from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import CustomerPrincipal, hash_password
from app.domains.audit.models import AuditLog
from app.domains.conversations.models import Message, MessageSender, MessageStatus
from app.domains.conversations.service import ConversationService
from app.domains.handoffs.service import CustomerHandoffService
from app.domains.identities.models import StaffUser, TenantMembership, TenantRole
from tests.test_chat_api import issue_customer_token, setup_chat_application


async def _create_agents(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: object
) -> None:
    async with session_factory() as session:
        agent_a = StaffUser(
            email="agent-a@example.com",
            display_name="Agent A",
            password_hash=hash_password("agent-password"),
        )
        agent_b = StaffUser(
            email="agent-b@example.com",
            display_name="Agent B",
            password_hash=hash_password("agent-password"),
        )
        session.add_all([agent_a, agent_b])
        await session.flush()
        session.add_all(
            [
                TenantMembership(
                    tenant_id=tenant_id,
                    staff_user_id=agent_a.id,
                    role=TenantRole.AGENT,
                ),
                TenantMembership(
                    tenant_id=tenant_id,
                    staff_user_id=agent_b.id,
                    role=TenantRole.AGENT,
                ),
            ]
        )
        await session.commit()


async def _agent_login(client: AsyncClient, email: str, tenant_id: str) -> dict[str, str]:
    response = await client.post(
        "/v1/admin/auth/login",
        json={
            "email": email,
            "password": "agent-password",
            "tenant_id": tenant_id,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_handoff_pauses_ai_has_single_owner_and_closes_conversation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await setup_chat_application(client, session_factory)
    tenant_id = setup["tenant"].id
    await _create_agents(session_factory, tenant_id)
    agent_a = await _agent_login(client, "agent-a@example.com", str(tenant_id))
    agent_b = await _agent_login(client, "agent-b@example.com", str(tenant_id))
    customer_token = await issue_customer_token(client, setup["api_key"], "handoff-user")
    customer = {"Authorization": f"Bearer {customer_token}"}
    conversation = await client.post("/v1/chat/sessions", headers=customer, json={})
    assert conversation.status_code == 201, conversation.text
    conversation_id = conversation.json()["id"]

    initial_chat = await client.post(
        f"/v1/chat/sessions/{conversation_id}/messages",
        headers=customer,
        json={"content": "I cannot update my account"},
    )
    assert initial_chat.status_code == 200, initial_chat.text

    requested = await client.post(
        f"/v1/chat/sessions/{conversation_id}/handoff",
        headers=customer,
        json={"reason": "I need an account specialist"},
    )
    assert requested.status_code == 201, requested.text
    assert requested.json()["status"] == "pending"
    assert "user: I cannot update my account" in requested.json()["summary"]
    handoff_id = requested.json()["id"]

    duplicate = await client.post(
        f"/v1/chat/sessions/{conversation_id}/handoff",
        headers=customer,
        json={"reason": "duplicate request"},
    )
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["id"] == handoff_id

    ai_blocked = await client.post(
        f"/v1/chat/sessions/{conversation_id}/messages",
        headers=customer,
        json={"content": "AI must not answer this"},
    )
    assert ai_blocked.status_code == 409
    assert ai_blocked.json()["code"] == "conversation_in_human_mode"

    queued_message = await client.post(
        f"/v1/chat/sessions/{conversation_id}/human-messages",
        headers={**customer, "Idempotency-Key": "human-message-1"},
        json={"content": "Here are more details"},
    )
    assert queued_message.status_code == 201, queued_message.text
    duplicate_message = await client.post(
        f"/v1/chat/sessions/{conversation_id}/human-messages",
        headers={**customer, "Idempotency-Key": "human-message-1"},
        json={"content": "must not create a second message"},
    )
    assert duplicate_message.json()["id"] == queued_message.json()["id"]

    queue = await client.get("/v1/admin/handoffs?status=pending", headers=agent_a)
    assert queue.status_code == 200, queue.text
    assert [item["id"] for item in queue.json()] == [handoff_id]

    accepted = await client.post(f"/v1/admin/handoffs/{handoff_id}/accept", headers=agent_a)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"

    lost_race = await client.post(f"/v1/admin/handoffs/{handoff_id}/accept", headers=agent_b)
    assert lost_race.status_code == 409
    assert lost_race.json()["code"] == "handoff_already_claimed"
    wrong_agent_reply = await client.post(
        f"/v1/admin/handoffs/{handoff_id}/messages",
        headers=agent_b,
        json={"content": "I did not accept this conversation"},
    )
    assert wrong_agent_reply.status_code == 409

    replied = await client.post(
        f"/v1/admin/handoffs/{handoff_id}/messages",
        headers=agent_a,
        json={"content": "I can help with that"},
    )
    assert replied.status_code == 201, replied.text
    assert replied.json()["sender"] == "agent"

    messages = await client.get(f"/v1/chat/sessions/{conversation_id}/messages", headers=customer)
    assert messages.status_code == 200, messages.text
    assert [message["sender"] for message in messages.json()] == [
        "user",
        "ai",
        "user",
        "agent",
    ]

    closed = await client.post(
        f"/v1/admin/handoffs/{handoff_id}/close",
        headers=agent_a,
        json={"reason": "resolved"},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    status_response = await client.get(
        f"/v1/chat/sessions/{conversation_id}/handoff", headers=customer
    )
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["status"] == "closed"

    after_close = await client.post(
        f"/v1/chat/sessions/{conversation_id}/human-messages",
        headers=customer,
        json={"content": "This must be rejected"},
    )
    assert after_close.status_code == 409
    assert after_close.json()["code"] == "conversation_closed"

    async with session_factory() as session:
        audited_actions = await session.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.action.in_(
                    [
                        "handoff.request",
                        "handoff.accept",
                        "handoff.message",
                        "handoff.close",
                    ]
                ),
            )
        )
        agent_audits = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.action.in_(["handoff.accept", "handoff.message", "handoff.close"]),
                )
            )
        )
    assert audited_actions == 4
    assert len(agent_audits) == 3
    assert all(log.details["conversation_id"] == conversation_id for log in agent_audits)


async def test_handoff_cancels_a_prepared_ai_reply_before_output(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await setup_chat_application(client, session_factory)
    external_user_id = "handoff-race-user"
    customer_token = await issue_customer_token(client, setup["api_key"], external_user_id)
    headers = {"Authorization": f"Bearer {customer_token}"}
    created = await client.post("/v1/chat/sessions", headers=headers, json={})
    assert created.status_code == 201, created.text
    conversation_id = UUID(created.json()["id"])
    principal = CustomerPrincipal(
        tenant_id=setup["tenant"].id,
        application_id=UUID(setup["application"]["id"]),
        external_user_id=external_user_id,
        scopes=("chat:write", "chat:read", "handoff:create"),
        token_id=uuid4(),
    )

    async with session_factory() as chat_session:
        service = ConversationService(chat_session)
        prepared = await service.prepare_chat(
            principal=principal,
            conversation_id=conversation_id,
            content="Can you answer before the agent joins?",
            idempotency_key="handoff-race-message",
        )
        async with session_factory() as handoff_session:
            await CustomerHandoffService(handoff_session).request(
                principal=principal,
                conversation_id=conversation_id,
                reason="I want a human now",
                request_id="handoff-race",
            )

        events = [event async for event in service.stream_chat(prepared)]

    assert all("event: message.delta" not in event for event in events)
    assert any("ai_reply_cancelled" in event for event in events)
    async with session_factory() as verification_session:
        assistant = await verification_session.scalar(
            select(Message).where(
                Message.tenant_id == principal.tenant_id,
                Message.conversation_id == conversation_id,
                Message.sender == MessageSender.AI,
            )
        )
    assert assistant is not None
    assert assistant.status == MessageStatus.FAILED
    assert assistant.error_code == "ai_reply_cancelled"
