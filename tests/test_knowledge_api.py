from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from _pytest.monkeypatch import MonkeyPatch
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.core.security import StaffPrincipal, hash_password
from app.domains.audit.models import AuditLog
from app.domains.conversations.models import (
    Conversation,
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
from app.domains.knowledge.parsing import _tokens, chunk_text, lexicalize
from app.domains.knowledge.repository import KnowledgeRepository
from app.domains.knowledge.service import DocumentService, IngestionService
from app.domains.tenants.models import Tenant
from app.providers.storage.memory import MemoryObjectStorage


def test_chinese_customer_wording_expands_to_retrieval_terms() -> None:
    terms = lexicalize("下单后可以马上去门店拿货吗").split()
    assert {"订单", "自提", "到店"} <= set(terms)
    assert {"节日", "商品"} <= set(lexicalize("节日商品退货期限").split())


def test_chunking_uses_token_overlap_and_preserves_table_rows() -> None:
    chunks = chunk_text(
        " ".join(f"word{index}" for index in range(120)),
        target_tokens=40,
        max_tokens=50,
    )

    assert len(chunks) >= 3
    assert all(len(_tokens(chunk.content)) <= 50 for chunk in chunks)
    assert _tokens(chunks[0].content)[-4:] == _tokens(chunks[1].content)[:4]

    rows = [
        "| Product | Return window |",
        "| --- | --- |",
        *[f"| Item {index} | {30 + index} days |" for index in range(12)],
    ]
    table_chunks = chunk_text("\n".join(rows), target_tokens=30, max_tokens=40)
    assert all(any(row in chunk.content for chunk in table_chunks) for row in rows)

    faq_chunks = chunk_text(
        " ".join(f"context{index}" for index in range(38))
        + "\n\nQuestion: How long is the return window?"
        + "\n\nAnswer: The return window is 30 days.",
        target_tokens=40,
        max_tokens=55,
    )
    assert any(
        "Question: How long is the return window?" in chunk.content
        and "Answer: The return window is 30 days." in chunk.content
        for chunk in faq_chunks
    )


def test_rrf_score_is_the_primary_fusion_order() -> None:
    documents = [KnowledgeDocument(id=uuid4(), title=f"Document {index}") for index in range(3)]
    chunks = [KnowledgeChunk(id=uuid4(), content=f"Chunk {index}") for index in range(3)]

    results = KnowledgeRepository._fuse(
        [(chunks[0], documents[0], 0.1), (chunks[1], documents[1], 0.2)],
        [(chunks[1], documents[1], 0.2), (chunks[2], documents[2], 0.95)],
        3,
    )

    assert results[0].chunk.id == chunks[1].id


def test_restore_conflict_follows_deleted_intermediate_versions() -> None:
    first = KnowledgeDocument(id=uuid4(), status=DocumentStatus.DISABLED)
    deleted_middle = KnowledgeDocument(
        id=uuid4(),
        supersedes_document_id=first.id,
        status=DocumentStatus.DELETED,
    )
    latest = KnowledgeDocument(
        id=uuid4(),
        supersedes_document_id=deleted_middle.id,
        status=DocumentStatus.READY,
    )

    assert DocumentService._has_ready_version_conflict(
        first,
        [first, deleted_middle, latest],
    )


async def _create_tenant_admins(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Tenant, Tenant]:
    async with session_factory() as session:
        tenant_a = Tenant(name="Knowledge Tenant A", slug="knowledge-tenant-a")
        tenant_b = Tenant(name="Knowledge Tenant B", slug="knowledge-tenant-b")
        admin = StaffUser(
            email="knowledge-admin@example.com",
            display_name="Knowledge Admin",
            password_hash=hash_password("knowledge-password"),
        )
        session.add_all([tenant_a, tenant_b, admin])
        await session.flush()
        session.add_all(
            [
                TenantMembership(
                    tenant_id=tenant_a.id,
                    staff_user_id=admin.id,
                    role=TenantRole.TENANT_ADMIN,
                ),
                TenantMembership(
                    tenant_id=tenant_b.id,
                    staff_user_id=admin.id,
                    role=TenantRole.TENANT_ADMIN,
                ),
            ]
        )
        await session.commit()
        return tenant_a, tenant_b


async def _login(client: AsyncClient, body: Mapping[str, Any]) -> str:
    response = await client.post("/v1/admin/auth/login", json=dict(body))
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


async def _prepare_knowledge_base(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    application = await client.post(
        "/v1/admin/applications",
        headers=headers,
        json={"name": "Knowledge Chat"},
    )
    assert application.status_code == 201, application.text

    account = await client.post(
        "/v1/admin/ai/provider-accounts",
        headers=headers,
        json={"name": "Knowledge Fake", "kind": "fake"},
    )
    assert account.status_code == 201, account.text
    tested = await client.post(
        f"/v1/admin/ai/provider-accounts/{account.json()['id']}/test",
        headers=headers,
    )
    assert tested.status_code == 200, tested.text

    embedding = await client.post(
        "/v1/admin/ai/model-configs",
        headers=headers,
        json={
            "provider_account_id": account.json()["id"],
            "name": "Knowledge Embedding",
            "model_name": "fake-embedding",
            "purpose": "embedding",
            "embedding_dimension": 32,
        },
    )
    assert embedding.status_code == 201, embedding.text

    knowledge_base = await client.post(
        "/v1/admin/knowledge-bases",
        headers=headers,
        json={
            "name": "Help Center",
            "description": "Public support content",
            "embedding_model_config_id": embedding.json()["id"],
        },
    )
    assert knowledge_base.status_code == 201, knowledge_base.text
    assert knowledge_base.json()["keyword_score_threshold"] == 0.15
    assert knowledge_base.json()["vector_similarity_threshold"] == 0.72

    bound = await client.put(
        "/v1/admin/knowledge-bases/"
        f"{knowledge_base.json()['id']}/applications/{application.json()['id']}",
        headers=headers,
    )
    assert bound.status_code == 204, bound.text
    bindings = await client.get(
        f"/v1/admin/knowledge-bases/{knowledge_base.json()['id']}/applications",
        headers=headers,
    )
    assert bindings.status_code == 200, bindings.text
    assert [item["id"] for item in bindings.json()] == [application.json()["id"]]
    return str(knowledge_base.json()["id"]), str(application.json()["id"])


async def test_document_ingestion_search_versioning_and_tenant_isolation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    memory_storage: MemoryObjectStorage,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.v1.knowledge._enqueue_ingestion", lambda *_: None)
    tenant_a, tenant_b = await _create_tenant_admins(session_factory)
    token_a = await _login(
        client,
        {
            "email": "knowledge-admin@example.com",
            "password": "knowledge-password",
            "tenant_id": str(tenant_a.id),
        },
    )
    token_b = await _login(
        client,
        {
            "email": "knowledge-admin@example.com",
            "password": "knowledge-password",
            "tenant_id": str(tenant_b.id),
        },
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    base_id, application_id = await _prepare_knowledge_base(client, headers_a)

    calibrated = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}",
        headers=headers_a,
        json={"keyword_score_threshold": 0.2, "vector_similarity_threshold": 0.7},
    )
    assert calibrated.status_code == 200, calibrated.text
    assert calibrated.json()["keyword_score_threshold"] == 0.2
    assert calibrated.json()["vector_similarity_threshold"] == 0.7

    uploaded = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/documents",
        headers=headers_a,
        data={"title": "Returns policy", "source_url": "https://docs.example.com/returns"},
        files={
            "file": (
                "returns.md",
                b"# Returns\n\nProducts may be returned within 30 days.",
                "text/markdown",
            )
        },
    )
    assert uploaded.status_code == 202, uploaded.text
    first_document_id = uploaded.json()["document"]["id"]
    assert uploaded.json()["job"]["status"] == "pending"
    assert next(iter(memory_storage.objects)).startswith(f"tenants/{tenant_a.id}/knowledge/")

    pending_delete = await client.delete(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}",
        headers=headers_a,
    )
    assert pending_delete.status_code == 409
    assert pending_delete.json()["code"] == "document_ingestion_in_progress"

    async with session_factory() as session:
        await IngestionService(session, memory_storage).process(
            tenant_id=tenant_a.id,
            document_id=UUID(uploaded.json()["document"]["id"]),
        )
        chunk = await session.scalar(
            select(KnowledgeChunk).where(
                KnowledgeChunk.tenant_id == tenant_a.id,
                KnowledgeChunk.document_id == UUID(uploaded.json()["document"]["id"]),
            )
        )
        assert chunk is not None
        assert chunk.source_locator == "https://docs.example.com/returns"
        assert "policy" in chunk.lexical_text.split()
        assert chunk.embedding_dimension == 32
        assert chunk.status.value == "active"

    detail = await client.get(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}",
        headers=headers_a,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["document"]["status"] == "ready"
    assert detail.json()["job"]["stage"] == "published"

    ready_retry = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/retry",
        headers=headers_a,
    )
    assert ready_retry.status_code == 409
    assert ready_retry.json()["code"] == "document_not_retryable"

    search = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/search",
        headers=headers_a,
        json={"query": "How many days are allowed for returns?", "top_k": 5},
    )
    assert search.status_code == 200, search.text
    assert search.json()
    assert "30 days" in search.json()[0]["content"]

    cross_tenant_disable = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/status",
        headers=headers_b,
        json={"status": "disabled"},
    )
    assert cross_tenant_disable.status_code == 404

    disabled = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/status",
        headers=headers_a,
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["can_restore"] is True
    assert disabled.json()["restore_block_reason"] is None
    disabled_again = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/status",
        headers=headers_a,
        json={"status": "disabled"},
    )
    assert disabled_again.status_code == 409
    assert disabled_again.json()["code"] == "document_status_transition_invalid"

    disabled_search = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/search",
        headers=headers_a,
        json={"query": "How many days are allowed for returns?", "top_k": 5},
    )
    assert disabled_search.status_code == 200, disabled_search.text
    assert disabled_search.json() == []
    async with session_factory() as session:
        disabled_chunk = await session.scalar(
            select(KnowledgeChunk).where(
                KnowledgeChunk.tenant_id == tenant_a.id,
                KnowledgeChunk.document_id == UUID(first_document_id),
            )
        )
        assert disabled_chunk is not None
        assert disabled_chunk.status == ChunkStatus.DISABLED

    restored = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/status",
        headers=headers_a,
        json={"status": "ready"},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "ready"
    assert restored.json()["can_restore"] is False
    restored_again = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/status",
        headers=headers_a,
        json={"status": "ready"},
    )
    assert restored_again.status_code == 409
    assert restored_again.json()["code"] == "document_status_transition_invalid"
    restored_search = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/search",
        headers=headers_a,
        json={"query": "How many days are allowed for returns?", "top_k": 5},
    )
    assert restored_search.status_code == 200, restored_search.text
    assert "30 days" in restored_search.json()[0]["content"]

    source_check_disable = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/status",
        headers=headers_a,
        json={"status": "disabled"},
    )
    assert source_check_disable.status_code == 200, source_check_disable.text
    first_object_key = next(key for key in memory_storage.objects if first_document_id in key)
    first_object = memory_storage.objects.pop(first_object_key)
    missing_source_restore = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/status",
        headers=headers_a,
        json={"status": "ready"},
    )
    assert missing_source_restore.status_code == 409
    assert missing_source_restore.json()["code"] == "document_restore_source_invalid"
    memory_storage.objects[first_object_key] = first_object

    source_restored = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/status",
        headers=headers_a,
        json={"status": "ready"},
    )
    assert source_restored.status_code == 200, source_restored.text
    index_check_disable = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/status",
        headers=headers_a,
        json={"status": "disabled"},
    )
    assert index_check_disable.status_code == 200, index_check_disable.text
    async with session_factory() as session:
        chunk = await session.scalar(
            select(KnowledgeChunk).where(
                KnowledgeChunk.tenant_id == tenant_a.id,
                KnowledgeChunk.document_id == UUID(first_document_id),
            )
        )
        assert chunk is not None
        chunk.embedding_version = "incompatible"
        await session.commit()
    incompatible_index_restore = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/status",
        headers=headers_a,
        json={"status": "ready"},
    )
    assert incompatible_index_restore.status_code == 409
    assert incompatible_index_restore.json()["code"] == "document_restore_index_invalid"
    async with session_factory() as session:
        chunk = await session.scalar(
            select(KnowledgeChunk).where(
                KnowledgeChunk.tenant_id == tenant_a.id,
                KnowledgeChunk.document_id == UUID(first_document_id),
            )
        )
        assert chunk is not None
        chunk.embedding_version = "v1"
        await session.commit()
    index_restored = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/status",
        headers=headers_a,
        json={"status": "ready"},
    )
    assert index_restored.status_code == 200, index_restored.text

    hidden = await client.get(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}",
        headers=headers_b,
    )
    assert hidden.status_code == 404

    replacement = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/documents",
        headers=headers_a,
        data={
            "title": "Returns policy",
            "source_url": "https://docs.example.com/returns",
            "replace_document_id": first_document_id,
        },
        files={
            "file": (
                "returns-v2.md",
                b"# Returns\n\nProducts may be returned within 45 days.",
                "text/markdown",
            )
        },
    )
    assert replacement.status_code == 202, replacement.text
    assert replacement.json()["document"]["version"] == 2

    async with session_factory() as session:
        await IngestionService(session, memory_storage).process(
            tenant_id=tenant_a.id,
            document_id=UUID(replacement.json()["document"]["id"]),
        )

    old_detail = await client.get(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}",
        headers=headers_a,
    )
    assert old_detail.json()["document"]["status"] == "disabled"
    assert old_detail.json()["document"]["can_restore"] is False
    assert (
        old_detail.json()["document"]["restore_block_reason"] == "document_restore_version_conflict"
    )
    old_version_restore = await client.patch(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{first_document_id}/status",
        headers=headers_a,
        json={"status": "ready"},
    )
    assert old_version_restore.status_code == 409
    assert old_version_restore.json()["code"] == "document_restore_version_conflict"
    async with session_factory() as session:
        old_chunk = await session.scalar(
            select(KnowledgeChunk).where(
                KnowledgeChunk.tenant_id == tenant_a.id,
                KnowledgeChunk.document_id == UUID(first_document_id),
            )
        )
        assert old_chunk is not None
        assert old_chunk.status == ChunkStatus.DISABLED
        lifecycle_audits = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.tenant_id == tenant_a.id,
                    AuditLog.resource_id == first_document_id,
                    AuditLog.action.in_(
                        ["knowledge_document.disable", "knowledge_document.restore"]
                    ),
                )
            )
        )
        assert [audit.action for audit in lifecycle_audits].count("knowledge_document.disable") == 3
        assert [audit.action for audit in lifecycle_audits].count("knowledge_document.restore") == 3
        assert all(
            audit.details["from_status"] != audit.details["to_status"] for audit in lifecycle_audits
        )
    new_search = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/search",
        headers=headers_a,
        json={"query": "How many days are allowed for returns?", "top_k": 5},
    )
    assert new_search.status_code == 200, new_search.text
    assert all("30 days" not in item["content"] for item in new_search.json())
    assert "45 days" in new_search.json()[0]["content"]

    replacement_id = replacement.json()["document"]["id"]
    replacement_object_key = next(key for key in memory_storage.objects if replacement_id in key)

    async with session_factory() as session:
        replacement_chunk = await session.scalar(
            select(KnowledgeChunk).where(
                KnowledgeChunk.tenant_id == tenant_a.id,
                KnowledgeChunk.document_id == UUID(replacement_id),
            )
        )
        assert replacement_chunk is not None
        end_user = EndUser(
            tenant_id=tenant_a.id,
            application_id=UUID(application_id),
            external_user_id="historical-citation-user",
        )
        session.add(end_user)
        await session.flush()
        conversation = Conversation(
            tenant_id=tenant_a.id,
            application_id=UUID(application_id),
            end_user_id=end_user.id,
        )
        session.add(conversation)
        await session.flush()
        historical_conversation_id = conversation.id
        message = Message(
            tenant_id=tenant_a.id,
            application_id=UUID(application_id),
            conversation_id=conversation.id,
            sender=MessageSender.AI,
            content="Products may be returned within 45 days.",
            status=MessageStatus.COMPLETED,
        )
        session.add(message)
        await session.flush()
        citation = Citation(
            tenant_id=tenant_a.id,
            message_id=message.id,
            document_id=UUID(replacement_id),
            chunk_id=replacement_chunk.id,
            quote=replacement_chunk.content,
            source_title="Returns policy",
            source_url="https://docs.example.com/returns",
            score=0.99,
        )
        session.add(citation)
        await session.commit()
        historical_citation_id = citation.id

    async with session_factory() as session:
        admin = await session.scalar(
            select(StaffUser).where(StaffUser.email == "knowledge-admin@example.com")
        )
        assert admin is not None
        actor = StaffPrincipal(
            user_id=admin.id,
            email=admin.email,
            is_platform_admin=False,
            tenant_id=tenant_a.id,
            role=TenantRole.TENANT_ADMIN,
        )
        original_commit = session.commit

        async def fail_database_commit() -> None:
            raise RuntimeError("forced database commit failure")

        monkeypatch.setattr(session, "commit", fail_database_commit)
        with pytest.raises(RuntimeError, match="forced database commit failure"):
            await DocumentService(session, memory_storage).delete(
                tenant_id=tenant_a.id,
                base_id=UUID(base_id),
                document_id=UUID(replacement_id),
                actor=actor,
                request_id="commit-failure-test",
            )
        monkeypatch.setattr(session, "commit", original_commit)

    assert replacement_object_key in memory_storage.objects
    after_commit_failure = await client.get(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{replacement_id}",
        headers=headers_a,
    )
    assert after_commit_failure.status_code == 200
    assert after_commit_failure.json()["document"]["status"] == "ready"
    async with session_factory() as session:
        delete_audits = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.tenant_id == tenant_a.id,
                    AuditLog.resource_id == replacement_id,
                    AuditLog.action == "knowledge_document.delete",
                )
            )
        )
        assert delete_audits == []

    original_delete = memory_storage.delete

    async def fail_object_delete(_: str) -> None:
        raise AppError(
            status_code=503,
            code="object_storage_delete_failed",
            title="Object storage unavailable",
            detail="The object could not be deleted.",
        )

    monkeypatch.setattr(memory_storage, "delete", fail_object_delete)
    failed_delete = await client.delete(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{replacement_id}",
        headers=headers_a,
    )
    assert failed_delete.status_code == 503
    assert replacement_object_key in memory_storage.objects

    deleted_detail = await client.get(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{replacement_id}",
        headers=headers_a,
    )
    assert deleted_detail.status_code == 404
    deleted_search = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/search",
        headers=headers_a,
        json={"query": "How many days are allowed for returns?", "top_k": 5},
    )
    assert deleted_search.status_code == 200, deleted_search.text
    assert deleted_search.json() == []
    async with session_factory() as session:
        deleted_document = await session.get(KnowledgeDocument, UUID(replacement_id))
        assert deleted_document is not None
        assert deleted_document.status == DocumentStatus.DELETED
        assert deleted_document.object_cleanup_pending is True
        assert deleted_document.object_cleanup_attempts == 1
        assert deleted_document.object_cleanup_error
        deleted_chunk = await session.scalar(
            select(KnowledgeChunk).where(
                KnowledgeChunk.tenant_id == tenant_a.id,
                KnowledgeChunk.document_id == UUID(replacement_id),
            )
        )
        assert deleted_chunk is not None
        assert deleted_chunk.status == ChunkStatus.DISABLED
        assert await session.get(Citation, historical_citation_id) is not None
        assert (
            await KnowledgeRepository(session).get_citation_document(
                tenant_id=tenant_a.id,
                application_id=UUID(application_id),
                conversation_id=historical_conversation_id,
                citation_id=historical_citation_id,
            )
            is None
        )
        delete_audits = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.tenant_id == tenant_a.id,
                    AuditLog.resource_id == replacement_id,
                    AuditLog.action == "knowledge_document.delete",
                )
            )
        )
        assert len(delete_audits) == 1

    monkeypatch.setattr(memory_storage, "delete", original_delete)
    async with session_factory() as session:
        cleanup_result = await DocumentService(session, memory_storage).cleanup_pending_objects()
    assert cleanup_result == {"selected": 1, "completed": 1, "failed": 0}
    assert not any(replacement_id in key for key in memory_storage.objects)
    async with session_factory() as session:
        cleaned_document = await session.get(KnowledgeDocument, UUID(replacement_id))
        assert cleaned_document is not None
        assert cleaned_document.object_cleanup_pending is False
        assert cleaned_document.object_cleanup_attempts == 1
        assert cleaned_document.object_cleanup_error is None
        assert await session.get(Citation, historical_citation_id) is not None
    idempotent_delete = await client.delete(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{replacement_id}",
        headers=headers_a,
    )
    assert idempotent_delete.status_code == 204


async def test_upload_rejects_unsupported_document_type(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.v1.knowledge._enqueue_ingestion", lambda *_: None)
    tenant, _ = await _create_tenant_admins(session_factory)
    token = await _login(
        client,
        {
            "email": "knowledge-admin@example.com",
            "password": "knowledge-password",
            "tenant_id": str(tenant.id),
        },
    )
    headers = {"Authorization": f"Bearer {token}"}
    base_id, _ = await _prepare_knowledge_base(client, headers)

    response = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/documents",
        headers=headers,
        data={"title": "Executable"},
        files={"file": ("payload.exe", b"not really executable", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "document_type_unsupported"

    invalid_utf8 = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/documents",
        headers=headers,
        data={"title": "Invalid text"},
        files={"file": ("invalid.txt", b"\xff\xfe", "text/plain")},
    )
    assert invalid_utf8.status_code == 422
    assert invalid_utf8.json()["code"] == "document_encoding_invalid"

    fake_pdf = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/documents",
        headers=headers,
        data={"title": "Fake PDF"},
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )
    assert fake_pdf.status_code == 422
    assert fake_pdf.json()["code"] == "document_content_invalid"

    unsafe_source = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/documents",
        headers=headers,
        data={"title": "Unsafe source", "source_url": "javascript:alert(document.domain)"},
        files={"file": ("unsafe-source.md", b"# Safe document content", "text/markdown")},
    )
    assert unsafe_source.status_code == 422
    assert unsafe_source.json()["code"] == "source_url_invalid"


async def test_upload_enforces_content_deduplication_and_tenant_quotas(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.v1.knowledge._enqueue_ingestion", lambda *_: None)
    tenant, _ = await _create_tenant_admins(session_factory)
    token = await _login(
        client,
        {
            "email": "knowledge-admin@example.com",
            "password": "knowledge-password",
            "tenant_id": str(tenant.id),
        },
    )
    headers = {"Authorization": f"Bearer {token}"}
    base_id, _ = await _prepare_knowledge_base(client, headers)

    first_content = b"# Returns\n\nProducts can be returned within 30 days."
    first = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/documents",
        headers=headers,
        data={"title": "Returns"},
        files={"file": ("returns.md", first_content, "text/markdown")},
    )
    assert first.status_code == 202, first.text

    duplicate = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/documents",
        headers=headers,
        data={"title": "Returns duplicate"},
        files={"file": ("returns-copy.md", first_content, "text/markdown")},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "document_content_duplicate"

    monkeypatch.setattr(
        "app.domains.knowledge.service.get_settings",
        lambda: SimpleNamespace(
            knowledge_document_limit_per_tenant=1,
            knowledge_storage_limit_bytes_per_tenant=1024 * 1024,
        ),
    )
    over_document_quota = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/documents",
        headers=headers,
        data={"title": "Shipping"},
        files={
            "file": (
                "shipping.md",
                b"# Shipping\n\nOrders ship within two business days.",
                "text/markdown",
            )
        },
    )
    assert over_document_quota.status_code == 409
    assert over_document_quota.json()["code"] == "knowledge_document_quota_exceeded"

    monkeypatch.setattr(
        "app.domains.knowledge.service.get_settings",
        lambda: SimpleNamespace(
            knowledge_document_limit_per_tenant=10,
            knowledge_storage_limit_bytes_per_tenant=len(first_content) + 10,
        ),
    )
    over_storage_quota = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/documents",
        headers=headers,
        data={"title": "Warranty"},
        files={
            "file": (
                "warranty.md",
                b"# Warranty\n\nWarranty coverage lasts for one full year.",
                "text/markdown",
            )
        },
    )
    assert over_storage_quota.status_code == 413
    assert over_storage_quota.json()["code"] == "knowledge_storage_quota_exceeded"
