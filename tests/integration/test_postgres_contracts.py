from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

import app.models  # noqa: F401
from app.core.errors import AppError
from app.core.security import CustomerPrincipal, StaffPrincipal
from app.domains.applications.models import Application
from app.domains.audit.models import AuditLog
from app.domains.conversations.models import Conversation, ConversationMode, EndUser, Message
from app.domains.conversations.repository import ConversationRepository
from app.domains.conversations.service import ConversationService, PreparedChat
from app.domains.handoffs.models import HandoffRequest, HandoffStatus
from app.domains.handoffs.service import AgentHandoffService, CustomerHandoffService
from app.domains.identities.models import StaffUser, TenantMembership, TenantRole
from app.domains.knowledge.models import (
    DocumentStatus,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.domains.knowledge.repository import KnowledgeRepository
from app.domains.knowledge.service import DocumentService, KnowledgeBaseService
from app.domains.model_gateway.models import (
    AIModelConfig,
    AIProviderAccount,
    ApplicationModelBinding,
    ModelPurpose,
    ModelStatus,
    ProviderKind,
    ProviderScope,
    ProviderStatus,
)
from app.domains.tenants.models import Tenant
from app.infrastructure.database.base import Base
from app.providers.storage.memory import MemoryObjectStorage
from app.workers.knowledge import _document_lock_id

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def postgres_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for PostgreSQL integration tests")

    schema = f"test_{uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    async with admin_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.execute(CreateSchema(schema))

    scoped_engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": f"{schema},public"}},
    )
    try:
        async with scoped_engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    checkfirst=False,
                )
            )
        yield async_sessionmaker(scoped_engine, expire_on_commit=False)
    finally:
        await scoped_engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await admin_engine.dispose()


async def _create_search_fixture(
    session: AsyncSession,
    *,
    slug: str,
    content: str,
    vector: list[float],
) -> tuple[Tenant, KnowledgeBase]:
    tenant = Tenant(name=slug, slug=slug)
    session.add(tenant)
    await session.flush()
    provider = AIProviderAccount(
        tenant_id=tenant.id,
        scope=ProviderScope.TENANT,
        name="fake-embedding",
        kind=ProviderKind.FAKE,
        status=ProviderStatus.READY,
    )
    session.add(provider)
    await session.flush()
    model = AIModelConfig(
        tenant_id=tenant.id,
        provider_account_id=provider.id,
        name="embedding",
        model_name="fake-embedding-v1",
        purpose=ModelPurpose.EMBEDDING,
        embedding_dimension=3,
        status=ModelStatus.ACTIVE,
    )
    session.add(model)
    await session.flush()
    knowledge_base = KnowledgeBase(
        tenant_id=tenant.id,
        name="private-knowledge",
        embedding_model_config_id=model.id,
        embedding_model_name=model.model_name,
        embedding_dimension=3,
        embedding_version="integration-v1",
    )
    session.add(knowledge_base)
    await session.flush()
    document = KnowledgeDocument(
        tenant_id=tenant.id,
        knowledge_base_id=knowledge_base.id,
        version=1,
        title=f"{slug} private document",
        source_filename="private.txt",
        source_url=f"https://{slug}.invalid/private",
        mime_type="text/plain",
        byte_size=len(content.encode()),
        object_key=f"tenants/{tenant.id}/private.txt",
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        status=DocumentStatus.READY,
    )
    session.add(document)
    await session.flush()
    session.add(
        KnowledgeChunk(
            tenant_id=tenant.id,
            knowledge_base_id=knowledge_base.id,
            document_id=document.id,
            document_version=1,
            chunk_index=0,
            content=content,
            heading_path=["private"],
            source_locator=document.source_url or document.source_filename,
            lexical_text=content,
            lexical_vector=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            embedding=vector,
            embedding_model=model.model_name,
            embedding_version=knowledge_base.embedding_version,
            embedding_dimension=knowledge_base.embedding_dimension,
            chunking_version="integration-v1",
        )
    )
    await session.flush()
    await session.execute(
        update(KnowledgeChunk)
        .where(
            KnowledgeChunk.tenant_id == tenant.id,
            KnowledgeChunk.document_id == document.id,
        )
        .values(lexical_vector=func.to_tsvector("simple", KnowledgeChunk.lexical_text))
    )
    return tenant, knowledge_base


async def test_postgres_hybrid_search_enforces_tenant_and_base_filters(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        tenant_a, base_a = await _create_search_fixture(
            session,
            slug="search-tenant-a",
            content="tenant_a private refund policy",
            vector=[1.0, 0.0, 0.0],
        )
        tenant_b, base_b = await _create_search_fixture(
            session,
            slug="search-tenant-b",
            content="tenant_b private refund policy",
            vector=[1.0, 0.0, 0.0],
        )
        await session.commit()

        repository = KnowledgeRepository(session)
        own_results = await repository.search(
            tenant_id=tenant_a.id,
            base_id=base_a.id,
            query_vector=[1.0, 0.0, 0.0],
            lexical_query="tenant_a refund",
            limit=5,
        )
        wrong_base_results = await repository.search(
            tenant_id=tenant_a.id,
            base_id=base_b.id,
            query_vector=[1.0, 0.0, 0.0],
            lexical_query="tenant_b refund",
            limit=5,
        )
        wrong_tenant_results = await repository.search(
            tenant_id=tenant_b.id,
            base_id=base_a.id,
            query_vector=[1.0, 0.0, 0.0],
            lexical_query="tenant_a refund",
            limit=5,
        )

    assert [result.document.tenant_id for result in own_results] == [tenant_a.id]
    assert own_results[0].keyword_score > 0
    assert wrong_base_results == []
    assert wrong_tenant_results == []


async def _create_handoff_fixture(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID, tuple[StaffPrincipal, StaffPrincipal]]:
    async with session_factory() as session:
        tenant = Tenant(name="Handoff concurrency", slug="handoff-concurrency")
        session.add(tenant)
        await session.flush()
        application = Application(
            tenant_id=tenant.id,
            name="handoff-web",
            public_key=f"pk_{uuid4().hex}",
            allowed_origins=["https://handoff.invalid"],
        )
        agents = [
            StaffUser(
                email=f"postgres-agent-{index}@example.com",
                display_name=f"Agent {index}",
                password_hash="integration-test-not-used",
            )
            for index in range(2)
        ]
        session.add_all([application, *agents])
        await session.flush()
        session.add_all(
            [
                TenantMembership(
                    tenant_id=tenant.id,
                    staff_user_id=agent.id,
                    role=TenantRole.AGENT,
                )
                for agent in agents
            ]
        )
        end_user = EndUser(
            tenant_id=tenant.id,
            application_id=application.id,
            external_user_id="concurrent-user",
        )
        session.add(end_user)
        await session.flush()
        conversation = Conversation(
            tenant_id=tenant.id,
            application_id=application.id,
            end_user_id=end_user.id,
            mode=ConversationMode.HUMAN,
        )
        session.add(conversation)
        await session.flush()
        handoff = HandoffRequest(
            tenant_id=tenant.id,
            application_id=application.id,
            conversation_id=conversation.id,
            requested_by_end_user_id=end_user.id,
            reason="concurrency check",
            summary="Customer requested a human agent.",
        )
        session.add(handoff)
        await session.commit()
        principals = tuple(
            StaffPrincipal(
                user_id=agent.id,
                email=agent.email,
                is_platform_admin=False,
                tenant_id=tenant.id,
                role=TenantRole.AGENT,
            )
            for agent in agents
        )
        return tenant.id, handoff.id, principals  # type: ignore[return-value]


async def test_postgres_allows_exactly_one_agent_to_accept_a_handoff(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_id, handoff_id, principals = await _create_handoff_fixture(postgres_session_factory)

    async def accept(principal: StaffPrincipal) -> tuple[str, UUID]:
        async with postgres_session_factory() as session:
            try:
                handoff = await AgentHandoffService(session).accept(
                    actor=principal,
                    handoff_id=handoff_id,
                    request_id=f"race-{principal.user_id}",
                )
                return "accepted", handoff.assigned_staff_user_id or principal.user_id
            except AppError as exc:
                await session.rollback()
                return exc.code, principal.user_id

    outcomes = await asyncio.gather(*(accept(principal) for principal in principals))

    assert sorted(outcome[0] for outcome in outcomes) == ["accepted", "handoff_already_claimed"]
    winner = next(agent_id for status, agent_id in outcomes if status == "accepted")
    async with postgres_session_factory() as session:
        handoff = await session.scalar(
            select(HandoffRequest).where(
                HandoffRequest.tenant_id == tenant_id,
                HandoffRequest.id == handoff_id,
            )
        )
        accept_audits = int(
            await session.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.action == "handoff.accept",
                    AuditLog.resource_id == str(handoff_id),
                )
            )
            or 0
        )

    assert handoff is not None
    assert handoff.status == HandoffStatus.ACCEPTED
    assert handoff.assigned_staff_user_id == winner
    assert accept_audits == 1


async def _create_customer_conversation_fixture(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[CustomerPrincipal, UUID]:
    async with session_factory() as session:
        tenant = Tenant(name="Customer lock", slug="customer-lock")
        session.add(tenant)
        await session.flush()
        application = Application(
            tenant_id=tenant.id,
            name="customer-lock-web",
            public_key=f"pk_{uuid4().hex}",
            allowed_origins=["https://customer-lock.invalid"],
        )
        session.add(application)
        await session.flush()
        end_user = EndUser(
            tenant_id=tenant.id,
            application_id=application.id,
            external_user_id="customer-lock-user",
        )
        session.add(end_user)
        await session.flush()
        conversation = Conversation(
            tenant_id=tenant.id,
            application_id=application.id,
            end_user_id=end_user.id,
            mode=ConversationMode.AI,
        )
        session.add(conversation)
        await session.commit()
        return (
            CustomerPrincipal(
                tenant_id=tenant.id,
                application_id=application.id,
                external_user_id=end_user.external_user_id,
                scopes=("chat:read", "chat:write", "handoff:create"),
                token_id=uuid4(),
            ),
            conversation.id,
        )


async def test_postgres_serializes_ai_finalization_and_handoff_request(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    principal, conversation_id = await _create_customer_conversation_fixture(
        postgres_session_factory
    )

    async def request_handoff() -> HandoffRequest:
        async with postgres_session_factory() as session:
            return await CustomerHandoffService(session).request(
                principal=principal,
                conversation_id=conversation_id,
                reason="customer_requested_handoff",
                request_id="handoff-lock-contract",
            )

    async with postgres_session_factory() as ai_session:
        state = await ConversationRepository(ai_session).get_conversation_state(
            tenant_id=principal.tenant_id,
            conversation_id=conversation_id,
            for_update=True,
        )
        assert state is not None

        handoff_task = asyncio.create_task(request_handoff())
        await asyncio.sleep(0.1)
        assert not handoff_task.done()

        await ai_session.commit()
        handoff = await asyncio.wait_for(handoff_task, timeout=2)

    assert handoff.status == HandoffStatus.PENDING
    async with postgres_session_factory() as session:
        conversation = await session.scalar(
            select(Conversation).where(
                Conversation.tenant_id == principal.tenant_id,
                Conversation.id == conversation_id,
            )
        )
    assert conversation is not None
    assert conversation.mode == ConversationMode.HUMAN


async def test_postgres_serializes_duplicate_document_ingestion_locks(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    lock_id = _document_lock_id(uuid4(), uuid4())

    async with postgres_session_factory() as first_session:
        await first_session.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": lock_id})
        async with postgres_session_factory() as second_session:
            second_acquired = await second_session.scalar(
                text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}
            )
            assert second_acquired is False

            await first_session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id}
            )
            second_acquired = await second_session.scalar(
                text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}
            )
            assert second_acquired is True
            await second_session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id}
            )


async def _create_chat_idempotency_fixture(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[CustomerPrincipal, UUID]:
    async with session_factory() as session:
        tenant = Tenant(name="Chat idempotency", slug="chat-idempotency")
        session.add(tenant)
        await session.flush()
        application = Application(
            tenant_id=tenant.id,
            name="chat-idempotency-web",
            public_key=f"pk_{uuid4().hex}",
            allowed_origins=["https://chat-idempotency.invalid"],
        )
        provider = AIProviderAccount(
            tenant_id=tenant.id,
            scope=ProviderScope.TENANT,
            name="fake-chat",
            kind=ProviderKind.FAKE,
            status=ProviderStatus.READY,
        )
        session.add_all([application, provider])
        await session.flush()
        model = AIModelConfig(
            tenant_id=tenant.id,
            provider_account_id=provider.id,
            name="chat",
            model_name="fake-chat-v1",
            purpose=ModelPurpose.CHAT,
            status=ModelStatus.ACTIVE,
        )
        end_user = EndUser(
            tenant_id=tenant.id,
            application_id=application.id,
            external_user_id="idempotent-customer",
        )
        session.add_all([model, end_user])
        await session.flush()
        session.add(
            ApplicationModelBinding(
                tenant_id=tenant.id,
                application_id=application.id,
                model_config_id=model.id,
                purpose=ModelPurpose.CHAT,
            )
        )
        conversation = Conversation(
            tenant_id=tenant.id,
            application_id=application.id,
            end_user_id=end_user.id,
        )
        session.add(conversation)
        await session.commit()
        return (
            CustomerPrincipal(
                tenant_id=tenant.id,
                application_id=application.id,
                external_user_id=end_user.external_user_id,
                scopes=("chat:read", "chat:write"),
                token_id=uuid4(),
            ),
            conversation.id,
        )


async def test_postgres_handles_concurrent_chat_idempotency_conflict(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal, conversation_id = await _create_chat_idempotency_fixture(postgres_session_factory)
    both_searches_started = asyncio.Event()
    arrival_lock = asyncio.Lock()
    arrivals = 0

    async def synchronized_empty_search(
        _service: KnowledgeBaseService, **_kwargs: object
    ) -> list[object]:
        nonlocal arrivals
        async with arrival_lock:
            arrivals += 1
            if arrivals == 2:
                both_searches_started.set()
        await asyncio.wait_for(both_searches_started.wait(), timeout=2)
        return []

    monkeypatch.setattr(
        KnowledgeBaseService,
        "search_for_application",
        synchronized_empty_search,
    )

    async def prepare() -> tuple[str, PreparedChat | None]:
        async with postgres_session_factory() as session:
            try:
                prepared = await ConversationService(session).prepare_chat(
                    principal=principal,
                    conversation_id=conversation_id,
                    content="What is the return policy?",
                    idempotency_key="same-concurrent-request",
                )
                return "accepted", prepared
            except AppError as exc:
                await session.rollback()
                return exc.code, None

    outcomes = await asyncio.gather(prepare(), prepare())

    assert sorted(status for status, _prepared in outcomes) == [
        "accepted",
        "idempotent_message_incomplete",
    ]
    async with postgres_session_factory() as session:
        message_count = int(
            await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.tenant_id == principal.tenant_id,
                    Message.conversation_id == conversation_id,
                )
            )
            or 0
        )
    assert message_count == 2


async def test_postgres_serializes_concurrent_duplicate_document_uploads(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        tenant, knowledge_base = await _create_search_fixture(
            session,
            slug="upload-deduplication",
            content="existing content",
            vector=[1.0, 0.0, 0.0],
        )
        await session.commit()

    actor = StaffPrincipal(
        user_id=uuid4(),
        email="upload-deduplication@example.com",
        is_platform_admin=False,
        tenant_id=tenant.id,
        role=TenantRole.TENANT_ADMIN,
    )
    storage = MemoryObjectStorage()
    upload_content = b"# Returns\n\nConcurrent uploads must create one document."

    async def upload() -> str:
        async with postgres_session_factory() as session:
            try:
                await DocumentService(session, storage).upload(
                    tenant_id=tenant.id,
                    base_id=knowledge_base.id,
                    title="Concurrent upload",
                    filename="concurrent.md",
                    mime_type="text/markdown",
                    content=upload_content,
                    source_url=None,
                    replace_document_id=None,
                    actor=actor,
                    request_id="concurrent-upload",
                )
                return "accepted"
            except AppError as exc:
                await session.rollback()
                return exc.code

    outcomes = await asyncio.gather(upload(), upload())

    assert sorted(outcomes) == ["accepted", "document_content_duplicate"]
    content_hash = hashlib.sha256(upload_content).hexdigest()
    async with postgres_session_factory() as session:
        document_count = int(
            await session.scalar(
                select(func.count(KnowledgeDocument.id)).where(
                    KnowledgeDocument.tenant_id == tenant.id,
                    KnowledgeDocument.knowledge_base_id == knowledge_base.id,
                    KnowledgeDocument.content_hash == content_hash,
                )
            )
            or 0
        )
    assert document_count == 1
    assert len(storage.objects) == 1
