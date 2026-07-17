from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.domains.applications.models import Application
from app.domains.conversations.models import (
    Conversation,
    ConversationMode,
    ConversationStatus,
    EndUser,
    Message,
    MessageSender,
    MessageStatus,
)
from app.domains.identities.models import StaffUser, TenantMembership, TenantRole
from app.domains.knowledge.models import (
    ChunkStatus,
    Citation,
    DocumentStatus,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.domains.tenants.models import Tenant
from tests.test_chat_api import setup_chat_application


async def _staff_headers(
    client: AsyncClient,
    *,
    email: str,
    password: str,
    tenant_id: UUID | None = None,
) -> dict[str, str]:
    payload: dict[str, str] = {"email": email, "password": password}
    if tenant_id is not None:
        payload["tenant_id"] = str(tenant_id)
    response = await client.post("/v1/admin/auth/login", json=payload)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _seed_admin_conversations(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, Any]:
    setup = await setup_chat_application(client, session_factory)
    tenant_id = setup["tenant"].id
    application_id = UUID(setup["application"]["id"])

    second_application = await client.post(
        "/v1/admin/applications",
        headers=setup["admin_headers"],
        json={"name": "Second chat application"},
    )
    assert second_application.status_code == 201, second_application.text
    second_application_id = UUID(second_application.json()["id"])

    embedding = await client.post(
        "/v1/admin/ai/model-configs",
        headers=setup["admin_headers"],
        json={
            "provider_account_id": setup["provider_account"]["id"],
            "name": "Conversation test embedding",
            "model_name": "fake-embedding",
            "purpose": "embedding",
            "embedding_dimension": 8,
        },
    )
    assert embedding.status_code == 201, embedding.text
    knowledge_base = await client.post(
        "/v1/admin/knowledge-bases",
        headers=setup["admin_headers"],
        json={
            "name": "Conversation test knowledge",
            "embedding_model_config_id": embedding.json()["id"],
        },
    )
    assert knowledge_base.status_code == 201, knowledge_base.text

    started_at = datetime.now(UTC) - timedelta(hours=1)
    async with session_factory() as session:
        agent = StaffUser(
            email="conversation-agent@example.com",
            display_name="Conversation Agent",
            password_hash=hash_password("staff-password"),
        )
        foreign_agent = StaffUser(
            email="foreign-conversation-agent@example.com",
            display_name="Foreign Conversation Agent",
            password_hash=hash_password("staff-password"),
        )
        platform_admin = StaffUser(
            email="conversation-platform@example.com",
            display_name="Conversation Platform Admin",
            password_hash=hash_password("platform-password"),
            is_platform_admin=True,
        )
        foreign_tenant = Tenant(name="Foreign conversation tenant", slug="foreign-conversations")
        session.add_all([agent, foreign_agent, platform_admin, foreign_tenant])
        await session.flush()

        foreign_application = Application(
            tenant_id=foreign_tenant.id,
            name="Foreign chat",
            public_key=f"pk_{uuid4().hex}",
            allowed_origins=[],
        )
        session.add_all(
            [
                foreign_application,
                TenantMembership(
                    tenant_id=tenant_id,
                    staff_user_id=agent.id,
                    role=TenantRole.AGENT,
                ),
                TenantMembership(
                    tenant_id=foreign_tenant.id,
                    staff_user_id=foreign_agent.id,
                    role=TenantRole.AGENT,
                ),
            ]
        )
        await session.flush()

        users = [
            EndUser(
                tenant_id=tenant_id,
                application_id=(second_application_id if index == 2 else application_id),
                external_user_id=f"visible-user-{index}",
            )
            for index in range(5)
        ]
        foreign_user = EndUser(
            tenant_id=foreign_tenant.id,
            application_id=foreign_application.id,
            external_user_id="foreign-user",
        )
        session.add_all([*users, foreign_user])
        await session.flush()

        conversations = [
            Conversation(
                tenant_id=tenant_id,
                application_id=(second_application_id if index == 2 else application_id),
                end_user_id=user.id,
                mode=ConversationMode.HUMAN if index == 3 else ConversationMode.AI,
                status=(ConversationStatus.CLOSED if index == 1 else ConversationStatus.OPEN),
                created_at=started_at + timedelta(minutes=index),
            )
            for index, user in enumerate(users)
        ]
        foreign_conversation = Conversation(
            tenant_id=foreign_tenant.id,
            application_id=foreign_application.id,
            end_user_id=foreign_user.id,
            created_at=started_at + timedelta(minutes=20),
        )
        session.add_all([*conversations, foreign_conversation])
        await session.flush()

        target = conversations[-1]
        messages = [
            Message(
                tenant_id=tenant_id,
                application_id=application_id,
                conversation_id=target.id,
                sender=MessageSender.USER,
                content="How long is the return window?",
                status=MessageStatus.COMPLETED,
                created_at=started_at + timedelta(minutes=30),
            ),
            Message(
                tenant_id=tenant_id,
                application_id=application_id,
                conversation_id=target.id,
                sender=MessageSender.AI,
                content="The return window is 30 days.",
                status=MessageStatus.COMPLETED,
                model_info={"grounding": "evidence", "evidence_count": 1},
                created_at=started_at + timedelta(minutes=31),
            ),
            Message(
                tenant_id=tenant_id,
                application_id=application_id,
                conversation_id=target.id,
                sender=MessageSender.USER,
                content="Thanks",
                status=MessageStatus.COMPLETED,
                created_at=started_at + timedelta(minutes=32),
            ),
        ]
        session.add_all(messages)
        await session.flush()

        document = KnowledgeDocument(
            tenant_id=tenant_id,
            knowledge_base_id=UUID(knowledge_base.json()["id"]),
            title="Return policy",
            source_filename="return-policy.md",
            source_url="https://docs.example.com/returns",
            mime_type="text/markdown",
            byte_size=42,
            object_key=f"tests/{uuid4().hex}/return-policy.md",
            content_hash="a" * 64,
            status=DocumentStatus.READY,
        )
        session.add(document)
        await session.flush()
        chunk = KnowledgeChunk(
            tenant_id=tenant_id,
            knowledge_base_id=document.knowledge_base_id,
            document_id=document.id,
            document_version=1,
            chunk_index=0,
            content="Products may be returned within 30 days.",
            heading_path=["Returns"],
            source_locator="line:1",
            lexical_text="products returned 30 days",
            lexical_vector="products returned 30 days",
            content_hash="b" * 64,
            embedding=[0.0] * 8,
            embedding_model="fake-embedding",
            embedding_version="v1",
            embedding_dimension=8,
            chunking_version="v1",
            status=ChunkStatus.ACTIVE,
        )
        session.add(chunk)
        await session.flush()
        session.add(
            Citation(
                tenant_id=tenant_id,
                message_id=messages[1].id,
                document_id=document.id,
                chunk_id=chunk.id,
                quote=chunk.content,
                source_title=document.title,
                source_url=document.source_url,
                score=0.99,
            )
        )
        await session.commit()

    return {
        **setup,
        "application_id": application_id,
        "second_application_id": second_application_id,
        "conversations": conversations,
        "foreign_tenant_id": foreign_tenant.id,
        "foreign_conversation_id": foreign_conversation.id,
        "messages": messages,
    }


async def test_admin_conversations_support_tenant_pagination_and_filters(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await _seed_admin_conversations(client, session_factory)
    agent_headers = await _staff_headers(
        client,
        email="conversation-agent@example.com",
        password="staff-password",
        tenant_id=seeded["tenant"].id,
    )

    applications = await client.get("/v1/admin/applications", headers=agent_headers)
    assert applications.status_code == 200, applications.text
    assert {item["id"] for item in applications.json()} == {
        str(seeded["application_id"]),
        str(seeded["second_application_id"]),
    }
    assert all("secret" not in item and "credentials" not in item for item in applications.json())

    first = await client.get("/v1/admin/conversations?limit=2", headers=agent_headers)
    assert first.status_code == 200, first.text
    assert [item["external_user_id"] for item in first.json()["items"]] == [
        "visible-user-4",
        "visible-user-3",
    ]
    assert first.json()["has_more"] is True
    assert first.json()["next_cursor"] == str(seeded["conversations"][3].id)

    second = await client.get(
        "/v1/admin/conversations",
        headers=agent_headers,
        params={"limit": 2, "before": first.json()["next_cursor"]},
    )
    third = await client.get(
        "/v1/admin/conversations",
        headers=agent_headers,
        params={"limit": 2, "before": second.json()["next_cursor"]},
    )
    assert [item["external_user_id"] for item in second.json()["items"]] == [
        "visible-user-2",
        "visible-user-1",
    ]
    assert [item["external_user_id"] for item in third.json()["items"]] == ["visible-user-0"]
    assert third.json()["has_more"] is False
    assert third.json()["next_cursor"] is None

    closed = await client.get(
        "/v1/admin/conversations?status=closed",
        headers=seeded["admin_headers"],
    )
    by_application = await client.get(
        "/v1/admin/conversations",
        headers=agent_headers,
        params={"application_id": str(seeded["second_application_id"])},
    )
    human = await client.get(
        "/v1/admin/conversations?mode=human",
        headers=agent_headers,
    )
    assert [item["external_user_id"] for item in closed.json()["items"]] == ["visible-user-1"]
    assert [item["external_user_id"] for item in by_application.json()["items"]] == [
        "visible-user-2"
    ]
    assert [item["external_user_id"] for item in human.json()["items"]] == ["visible-user-3"]

    invalid_cursor = await client.get(
        "/v1/admin/conversations",
        headers=agent_headers,
        params={"before": str(seeded["foreign_conversation_id"])},
    )
    assert invalid_cursor.status_code == 400
    assert invalid_cursor.json()["code"] == "conversation_cursor_invalid"


async def test_admin_conversation_detail_messages_citations_and_permissions(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await _seed_admin_conversations(client, session_factory)
    target_id = seeded["conversations"][-1].id
    foreign_headers = await _staff_headers(
        client,
        email="foreign-conversation-agent@example.com",
        password="staff-password",
        tenant_id=seeded["foreign_tenant_id"],
    )
    platform_headers = await _staff_headers(
        client,
        email="conversation-platform@example.com",
        password="platform-password",
    )

    detail = await client.get(
        f"/v1/admin/conversations/{target_id}",
        headers=seeded["admin_headers"],
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["external_user_id"] == "visible-user-4"
    assert detail.json()["application_id"] == str(seeded["application_id"])

    page = await client.get(
        f"/v1/admin/conversations/{target_id}/messages?limit=2",
        headers=seeded["admin_headers"],
    )
    assert page.status_code == 200, page.text
    assert [item["sender"] for item in page.json()["items"]] == ["ai", "user"]
    ai_message = page.json()["items"][0]
    assert ai_message["model_info"]["grounding"] == "evidence"
    assert ai_message["citations"] == [
        {
            "id": ai_message["citations"][0]["id"],
            "document_id": ai_message["citations"][0]["document_id"],
            "chunk_id": ai_message["citations"][0]["chunk_id"],
            "quote": "Products may be returned within 30 days.",
            "source_title": "Return policy",
            "source_url": "https://docs.example.com/returns",
            "score": 0.99,
        }
    ]
    assert page.json()["next_cursor"] == str(seeded["messages"][1].id)

    previous = await client.get(
        f"/v1/admin/conversations/{target_id}/messages",
        headers=seeded["admin_headers"],
        params={"limit": 2, "before": page.json()["next_cursor"]},
    )
    assert [item["content"] for item in previous.json()["items"]] == [
        "How long is the return window?"
    ]
    assert previous.json()["has_more"] is False

    for suffix in ("", "/messages"):
        hidden = await client.get(
            f"/v1/admin/conversations/{target_id}{suffix}",
            headers=foreign_headers,
        )
        assert hidden.status_code == 404
        assert hidden.json()["code"] == "conversation_not_found"

    foreign_list = await client.get("/v1/admin/conversations", headers=foreign_headers)
    assert [item["id"] for item in foreign_list.json()["items"]] == [
        str(seeded["foreign_conversation_id"])
    ]

    platform_denied = await client.get("/v1/admin/conversations", headers=platform_headers)
    assert platform_denied.status_code == 403
    assert platform_denied.json()["code"] == "agent_required"
    unauthenticated = await client.get("/v1/admin/conversations")
    assert unauthenticated.status_code == 401


def test_admin_conversation_routes_are_exposed_in_openapi(test_app: FastAPI) -> None:
    paths = test_app.openapi()["paths"]
    assert paths["/v1/admin/conversations"]["get"]["operationId"] == "listAdminConversations"
    assert (
        paths["/v1/admin/conversations/{conversation_id}"]["get"]["operationId"]
        == "getAdminConversation"
    )
    assert (
        paths["/v1/admin/conversations/{conversation_id}/messages"]["get"]["operationId"]
        == "listAdminConversationMessages"
    )
