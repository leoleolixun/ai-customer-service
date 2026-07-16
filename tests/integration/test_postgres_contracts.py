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
from app.core.security import StaffPrincipal
from app.domains.applications.models import Application
from app.domains.audit.models import AuditLog
from app.domains.conversations.models import Conversation, ConversationMode, EndUser
from app.domains.handoffs.models import HandoffRequest, HandoffStatus
from app.domains.handoffs.service import AgentHandoffService
from app.domains.identities.models import StaffUser, TenantMembership, TenantRole
from app.domains.knowledge.models import (
    DocumentStatus,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.domains.knowledge.repository import KnowledgeRepository
from app.domains.model_gateway.models import (
    AIModelConfig,
    AIProviderAccount,
    ModelPurpose,
    ModelStatus,
    ProviderKind,
    ProviderScope,
    ProviderStatus,
)
from app.domains.tenants.models import Tenant
from app.infrastructure.database.base import Base

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
            lexical_text=content,
            lexical_vector=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            embedding=vector,
            embedding_model=model.model_name,
            embedding_version=knowledge_base.embedding_version,
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
