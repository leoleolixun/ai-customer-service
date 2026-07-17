import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from _pytest.monkeypatch import MonkeyPatch
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.core.security import hash_password
from app.domains.conversations.models import Message, MessageSender, MessageStatus
from app.domains.conversations.schemas import ConversationLocale
from app.domains.conversations.service import HUMAN_REQUIRED_RESPONSE, ConversationService
from app.domains.identities.models import StaffUser, TenantMembership, TenantRole
from app.domains.knowledge.models import KnowledgeChunk, KnowledgeDocument
from app.domains.knowledge.repository import KnowledgeRepository, RetrievedChunk
from app.domains.knowledge.service import IngestionService
from app.domains.tenants.models import Tenant
from app.domains.usage.models import AIUsageRecord
from app.providers.llm.fake import FakeEmbeddingProvider
from app.providers.storage.memory import MemoryObjectStorage


def test_sensitive_requests_are_routed_to_human_support() -> None:
    assert ConversationService._requires_human("Please refund this order")
    assert ConversationService._requires_human("我要取消订单")
    assert not ConversationService._requires_human("What is your return policy?")
    assert "Contact an agent" in HUMAN_REQUIRED_RESPONSE
    assert "paused" not in HUMAN_REQUIRED_RESPONSE


def test_fixed_security_and_handoff_cases_are_preclassified() -> None:
    cases = [
        json.loads(line)
        for line in Path("eval/rag_v1.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    for case in cases:
        if case["primary_category"] == "handoff":
            assert ConversationService._requires_human(case["question"]), case["id"]
        if case["primary_category"] == "prompt_injection_or_unauthorized":
            assert ConversationService._requires_security_refusal(case["question"]), case["id"]
        if case["primary_category"] == "no_answer":
            assert ConversationService._requires_unverifiable_refusal(case["question"]), case["id"]


def test_fake_embedding_preserves_shared_chinese_terms() -> None:
    query = FakeEmbeddingProvider._vector("礼品卡有效期多久", 64)
    related = FakeEmbeddingProvider._vector("礼品卡激活后有效三年", 64)
    unrelated = FakeEmbeddingProvider._vector("工作区支持按年订阅", 64)

    assert KnowledgeRepository._cosine(query, related) > KnowledgeRepository._cosine(
        query, unrelated
    )


def test_conflicting_numeric_sources_are_detected() -> None:
    evidence = [
        RetrievedChunk(
            chunk=KnowledgeChunk(content="节日商品可以在 60 天内退货。"),
            document=KnowledgeDocument(id=uuid4(), title="节日退货公告 A"),
            score=1,
            vector_similarity=1,
            keyword_score=1,
        ),
        RetrievedChunk(
            chunk=KnowledgeChunk(content="节日商品可以在 90 天内退货。"),
            document=KnowledgeDocument(id=uuid4(), title="节日退货公告 B"),
            score=0.9,
            vector_similarity=0.9,
            keyword_score=0.9,
        ),
    ]
    assert ConversationService._has_conflicting_evidence("节日商品退货期限是多久?", evidence)


def test_unrelated_specific_policy_does_not_conflict_with_general_question() -> None:
    evidence = [
        RetrievedChunk(
            chunk=KnowledgeChunk(content="普通商品可以在签收后 30 天内退货。"),
            document=KnowledgeDocument(id=uuid4(), title="普通退货规则"),
            score=1,
            vector_similarity=0.8,
            keyword_score=0.5,
        ),
        RetrievedChunk(
            chunk=KnowledgeChunk(content="节日商品可以在签收后 60 天内退货。"),
            document=KnowledgeDocument(id=uuid4(), title="节日退货公告 A"),
            score=0.9,
            vector_similarity=0.7,
            keyword_score=0.3,
        ),
        RetrievedChunk(
            chunk=KnowledgeChunk(content="节日商品可以在签收后 90 天内退货。"),
            document=KnowledgeDocument(id=uuid4(), title="节日退货公告 B"),
            score=0.8,
            vector_similarity=0.7,
            keyword_score=0.3,
        ),
    ]

    assert not ConversationService._has_conflicting_evidence(
        "普通商品签收后多久可以退货?", evidence
    )


def test_evidence_gate_uses_the_threshold_attached_to_each_knowledge_base() -> None:
    rejected = RetrievedChunk(
        chunk=KnowledgeChunk(content="A"),
        document=KnowledgeDocument(id=uuid4(), title="Strict base"),
        score=0.9,
        vector_similarity=0.75,
        keyword_score=0,
        vector_similarity_threshold=0.8,
    )
    accepted = RetrievedChunk(
        chunk=KnowledgeChunk(content="B"),
        document=KnowledgeDocument(id=uuid4(), title="Calibrated base"),
        score=0.8,
        vector_similarity=0.73,
        keyword_score=0,
        vector_similarity_threshold=0.7,
    )

    assert ConversationService._evidence_gate([rejected, accepted]) == [accepted]


def test_evidence_gate_removes_candidates_far_below_the_best_match() -> None:
    relevant = RetrievedChunk(
        chunk=KnowledgeChunk(content="The relevant policy"),
        document=KnowledgeDocument(id=uuid4(), title="Relevant policy"),
        score=1,
        vector_similarity=0.6,
        keyword_score=0.5,
    )
    generic = RetrievedChunk(
        chunk=KnowledgeChunk(content="A generic policy"),
        document=KnowledgeDocument(id=uuid4(), title="Generic policy"),
        score=0.9,
        vector_similarity=0.6,
        keyword_score=0.3,
    )

    assert ConversationService._evidence_gate([relevant, generic]) == [relevant]


def test_chat_history_keeps_latest_messages_within_character_budget() -> None:
    messages = [
        Message(sender=MessageSender.USER, content="old" * 4_000),
        Message(sender=MessageSender.AI, content="middle" * 2_000),
        Message(sender=MessageSender.USER, content="latest" * 1_000),
    ]

    history = ConversationService._history(messages, max_chars=20_000)

    assert [message.role for message in history] == ["assistant", "user"]
    assert history[-1].content == "latest" * 1_000
    assert sum(len(message.content) for message in history) <= 20_000


def test_grounding_prompt_instructs_the_selected_response_language() -> None:
    english = ConversationService._grounding_prompt([], locale=ConversationLocale.EN)
    chinese = ConversationService._grounding_prompt([], locale=ConversationLocale.ZH_CN)

    assert "Respond in English" in english
    assert "Respond in Simplified Chinese" in chinese


def test_empty_provider_answer_is_not_persisted_as_success() -> None:
    with pytest.raises(AppError) as exc_info:
        ConversationService._validated_answer_content(["", "  "])

    assert exc_info.value.code == "model_provider_empty_response"


async def setup_chat_application(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, Any]:
    async with session_factory() as session:
        tenant = Tenant(name="Chat tenant", slug="chat-tenant")
        admin = StaffUser(
            email="chat-admin@example.com",
            display_name="Chat Admin",
            password_hash=hash_password("chat-admin-password"),
        )
        session.add_all([tenant, admin])
        await session.flush()
        session.add(
            TenantMembership(
                tenant_id=tenant.id,
                staff_user_id=admin.id,
                role=TenantRole.TENANT_ADMIN,
            )
        )
        await session.commit()

    login = await client.post(
        "/v1/admin/auth/login",
        json={
            "email": "chat-admin@example.com",
            "password": "chat-admin-password",
            "tenant_id": str(tenant.id),
        },
    )
    assert login.status_code == 200, login.text
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    application = await client.post(
        "/v1/admin/applications",
        headers=admin_headers,
        json={"name": "Chat", "allowed_origins": ["https://chat.example.com"]},
    )
    assert application.status_code == 201, application.text
    account = await client.post(
        "/v1/admin/ai/provider-accounts",
        headers=admin_headers,
        json={"name": "Fake", "kind": "fake"},
    )
    assert account.status_code == 201, account.text
    tested = await client.post(
        f"/v1/admin/ai/provider-accounts/{account.json()['id']}/test",
        headers=admin_headers,
    )
    assert tested.status_code == 200, tested.text
    model = await client.post(
        "/v1/admin/ai/model-configs",
        headers=admin_headers,
        json={
            "provider_account_id": account.json()["id"],
            "name": "Chat model",
            "model_name": "fake-chat",
            "purpose": "chat",
            "input_price_micros_per_million": 1000,
            "output_price_micros_per_million": 2000,
        },
    )
    assert model.status_code == 201, model.text
    activated = await client.post(
        f"/v1/admin/ai/model-configs/{model.json()['id']}/activate",
        headers=admin_headers,
        json={"application_id": application.json()["id"]},
    )
    assert activated.status_code == 200, activated.text
    credential = await client.post(
        f"/v1/admin/applications/{application.json()['id']}/credentials",
        headers=admin_headers,
        json={"scopes": ["customer_token:create"]},
    )
    assert credential.status_code == 201, credential.text
    return {
        "tenant": tenant,
        "application": application.json(),
        "admin_headers": admin_headers,
        "provider_account": account.json(),
        "api_key": credential.json()["api_key"],
    }


async def issue_customer_token(client: AsyncClient, api_key: str, user_id: str) -> str:
    response = await client.post(
        "/v1/customer-tokens",
        headers={"X-API-Key": api_key, "Origin": "https://chat.example.com"},
        json={"external_user_id": user_id},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


async def test_chat_sse_idempotency_and_user_isolation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await setup_chat_application(client, session_factory)
    token_a = await issue_customer_token(client, setup["api_key"], "customer-a")
    token_b = await issue_customer_token(client, setup["api_key"], "customer-b")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    created = await client.post("/v1/chat/sessions", headers=headers_a, json={})
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    hidden = await client.get(f"/v1/chat/sessions/{conversation_id}", headers=headers_b)
    assert hidden.status_code == 404

    streamed = await client.post(
        f"/v1/chat/sessions/{conversation_id}/messages",
        headers={**headers_a, "Idempotency-Key": "message-1"},
        json={"content": "Where is the documentation?"},
    )
    assert streamed.status_code == 200, streamed.text
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert streamed.text.index("event: message.started") < streamed.text.index(
        "event: message.delta"
    )
    assert streamed.text.index("event: message.delta") < streamed.text.index(
        "event: message.completed"
    )
    assert "enough verified information" in streamed.text
    assert '"citations":[]' in streamed.text

    replay = await client.post(
        f"/v1/chat/sessions/{conversation_id}/messages",
        headers={**headers_a, "Idempotency-Key": "message-1"},
        json={"content": "This different body must not create another reply"},
    )
    assert replay.status_code == 200, replay.text
    assert '"replay":true' in replay.text
    assert "event: message.delta" not in replay.text

    messages = await client.get(f"/v1/chat/sessions/{conversation_id}/messages", headers=headers_a)
    assert messages.status_code == 200, messages.text
    assert [message["sender"] for message in messages.json()] == ["user", "ai"]

    async with session_factory() as session:
        usage_count = await session.scalar(select(func.count(AIUsageRecord.id)))
    assert usage_count == 1

    model_calls = await client.get(
        "/v1/admin/usage/model-calls?status=completed",
        headers=setup["admin_headers"],
    )
    assert model_calls.status_code == 200, model_calls.text
    assert len(model_calls.json()) == 1
    assert model_calls.json()[0]["model_name"] == "fake-chat"
    assert model_calls.json()[0]["conversation_id"] == conversation_id


async def test_message_history_returns_latest_page_and_supports_before_cursor(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await setup_chat_application(client, session_factory)
    token = await issue_customer_token(client, setup["api_key"], "history-customer")
    headers = {"Authorization": f"Bearer {token}"}
    created = await client.post("/v1/chat/sessions", headers=headers, json={})
    assert created.status_code == 201, created.text
    conversation_id = UUID(created.json()["id"])

    started_at = datetime.now(UTC)
    async with session_factory() as session:
        session.add_all(
            [
                Message(
                    tenant_id=setup["tenant"].id,
                    application_id=UUID(setup["application"]["id"]),
                    conversation_id=conversation_id,
                    sender=MessageSender.USER,
                    content=f"history-{index:03d}",
                    status=MessageStatus.COMPLETED,
                    created_at=started_at + timedelta(microseconds=index),
                )
                for index in range(105)
            ]
        )
        await session.commit()

    default_page = await client.get(
        f"/v1/chat/sessions/{conversation_id}/messages",
        headers=headers,
    )
    assert default_page.status_code == 200, default_page.text
    assert len(default_page.json()) == 100
    assert default_page.json()[0]["content"] == "history-005"
    assert default_page.json()[-1]["content"] == "history-104"

    latest = await client.get(
        f"/v1/chat/sessions/{conversation_id}/messages?limit=10",
        headers=headers,
    )
    assert [item["content"] for item in latest.json()] == [
        f"history-{index:03d}" for index in range(95, 105)
    ]

    before = latest.json()[0]["id"]
    previous = await client.get(
        f"/v1/chat/sessions/{conversation_id}/messages?limit=10&before={before}",
        headers=headers,
    )
    assert [item["content"] for item in previous.json()] == [
        f"history-{index:03d}" for index in range(85, 95)
    ]

    invalid = await client.get(
        f"/v1/chat/sessions/{conversation_id}/messages?before={uuid4()}",
        headers=headers,
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "message_cursor_invalid"


async def test_chat_returns_localized_rule_based_refusal(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await setup_chat_application(client, session_factory)
    token = await issue_customer_token(client, setup["api_key"], "zh-customer")
    headers = {"Authorization": f"Bearer {token}"}
    created = await client.post("/v1/chat/sessions", headers=headers, json={})
    assert created.status_code == 201, created.text

    streamed = await client.post(
        f"/v1/chat/sessions/{created.json()['id']}/messages",
        headers=headers,
        json={"content": "下个月会发布什么新功能？", "locale": "zh-CN"},  # noqa: RUF001
    )

    assert streamed.status_code == 200, streamed.text
    assert "我没有足够的已验证信息" in streamed.text

    invalid = await client.post(
        f"/v1/chat/sessions/{created.json()['id']}/messages",
        headers=headers,
        json={"content": "测试", "locale": "fr"},
    )
    assert invalid.status_code == 422


async def test_chat_uses_only_bound_knowledge_and_returns_citations(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    memory_storage: MemoryObjectStorage,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.v1.knowledge._enqueue_ingestion", lambda *_: None)
    setup = await setup_chat_application(client, session_factory)
    admin_headers = setup["admin_headers"]
    embedding = await client.post(
        "/v1/admin/ai/model-configs",
        headers=admin_headers,
        json={
            "provider_account_id": setup["provider_account"]["id"],
            "name": "Chat knowledge embedding",
            "model_name": "fake-embedding",
            "purpose": "embedding",
            "embedding_dimension": 32,
        },
    )
    assert embedding.status_code == 201, embedding.text
    knowledge_base = await client.post(
        "/v1/admin/knowledge-bases",
        headers=admin_headers,
        json={
            "name": "Chat help center",
            "embedding_model_config_id": embedding.json()["id"],
        },
    )
    assert knowledge_base.status_code == 201, knowledge_base.text
    base_id = knowledge_base.json()["id"]
    bound = await client.put(
        f"/v1/admin/knowledge-bases/{base_id}/applications/{setup['application']['id']}",
        headers=admin_headers,
    )
    assert bound.status_code == 204, bound.text
    uploaded = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/documents",
        headers=admin_headers,
        data={"title": "Returns", "source_url": "https://docs.example.com/returns"},
        files={
            "file": (
                "returns.md",
                b"# Returns\n\nProducts may be returned within 30 days.",
                "text/markdown",
            )
        },
    )
    assert uploaded.status_code == 202, uploaded.text
    async with session_factory() as session:
        await IngestionService(session, memory_storage).process(
            tenant_id=setup["tenant"].id,
            document_id=UUID(uploaded.json()["document"]["id"]),
        )

    customer_token = await issue_customer_token(client, setup["api_key"], "rag-customer")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    conversation = await client.post("/v1/chat/sessions", headers=customer_headers, json={})
    assert conversation.status_code == 201, conversation.text
    conversation_id = conversation.json()["id"]
    streamed = await client.post(
        f"/v1/chat/sessions/{conversation_id}/messages",
        headers={**customer_headers, "Idempotency-Key": "rag-message-1"},
        json={"content": "How many days are returns allowed?"},
    )
    assert streamed.status_code == 200, streamed.text
    assert "Fake assistant: How many days are returns allowed?" in streamed.text
    assert '"source_title":"Returns"' in streamed.text
    assert '"source_url":"https://docs.example.com/returns"' in streamed.text

    messages = await client.get(
        f"/v1/chat/sessions/{conversation_id}/messages", headers=customer_headers
    )
    assert messages.status_code == 200, messages.text
    ai_message = next(message for message in messages.json() if message["sender"] == "ai")
    assert len(ai_message["citations"]) >= 1
    assert "30 days" in ai_message["citations"][0]["quote"]
    citation_id = ai_message["citations"][0]["id"]
    source = await client.get(
        f"/v1/chat/sessions/{conversation_id}/citations/{citation_id}/source",
        headers=customer_headers,
    )
    assert source.status_code == 200, source.text
    assert source.headers["content-type"].startswith("text/markdown")
    assert source.headers["cache-control"] == "private, no-store"
    assert "Products may be returned within 30 days." in source.text

    other_token = await issue_customer_token(client, setup["api_key"], "other-rag-customer")
    hidden_source = await client.get(
        f"/v1/chat/sessions/{conversation_id}/citations/{citation_id}/source",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert hidden_source.status_code == 404


async def test_customer_rate_limit_is_scoped_to_application_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await setup_chat_application(client, session_factory)
    updated = await client.patch(
        f"/v1/admin/applications/{setup['application']['id']}",
        headers=setup["admin_headers"],
        json={"rate_limit_per_minute": 2},
    )
    assert updated.status_code == 200, updated.text
    token = await issue_customer_token(client, setup["api_key"], "limited-user")
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post("/v1/chat/sessions", headers=headers, json={})
    assert created.status_code == 201, created.text
    fetched = await client.get(f"/v1/chat/sessions/{created.json()['id']}", headers=headers)
    assert fetched.status_code == 200, fetched.text
    messages = await client.get(
        f"/v1/chat/sessions/{created.json()['id']}/messages", headers=headers
    )
    assert messages.status_code == 200, messages.text
    second = await client.post("/v1/chat/sessions", headers=headers, json={})
    assert second.status_code == 201, second.text
    limited = await client.post("/v1/chat/sessions", headers=headers, json={})
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert limited.json()["code"] == "rate_limit_exceeded"


async def test_customer_feedback_is_owned_upserted_and_visible_to_admin(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await setup_chat_application(client, session_factory)
    token_a = await issue_customer_token(client, setup["api_key"], "feedback-user")
    token_b = await issue_customer_token(client, setup["api_key"], "other-user")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    conversation = await client.post("/v1/chat/sessions", headers=headers_a, json={})
    assert conversation.status_code == 201, conversation.text
    conversation_id = conversation.json()["id"]
    streamed = await client.post(
        f"/v1/chat/sessions/{conversation_id}/messages",
        headers=headers_a,
        json={"content": "Can this unsupported question be answered?"},
    )
    assert streamed.status_code == 200, streamed.text
    messages = await client.get(f"/v1/chat/sessions/{conversation_id}/messages", headers=headers_a)
    ai_message = next(item for item in messages.json() if item["sender"] == "ai")

    created = await client.post(
        f"/v1/chat/sessions/{conversation_id}/feedback",
        headers=headers_a,
        json={
            "message_id": ai_message["id"],
            "rating": "unhelpful",
            "comment": "  Missing policy  ",
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["comment"] == "Missing policy"

    updated = await client.post(
        f"/v1/chat/sessions/{conversation_id}/feedback",
        headers=headers_a,
        json={"message_id": ai_message["id"], "rating": "helpful"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["id"] == created.json()["id"]
    assert updated.json()["rating"] == "helpful"

    hidden = await client.post(
        f"/v1/chat/sessions/{conversation_id}/feedback",
        headers=headers_b,
        json={"message_id": ai_message["id"], "rating": "unhelpful"},
    )
    assert hidden.status_code == 404

    listed = await client.get("/v1/admin/feedback", headers=setup["admin_headers"])
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1
    assert listed.json()[0]["message_id"] == ai_message["id"]
    assert "verified information" in listed.json()[0]["message_excerpt"]
