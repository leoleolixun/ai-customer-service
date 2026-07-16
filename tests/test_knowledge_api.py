from collections.abc import Mapping
from typing import Any
from uuid import UUID

from _pytest.monkeypatch import MonkeyPatch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.core.security import hash_password
from app.domains.identities.models import StaffUser, TenantMembership, TenantRole
from app.domains.knowledge.parsing import lexicalize
from app.domains.knowledge.service import IngestionService
from app.domains.tenants.models import Tenant
from app.providers.storage.memory import MemoryObjectStorage


def test_chinese_customer_wording_expands_to_retrieval_terms() -> None:
    terms = lexicalize("下单后可以马上去门店拿货吗").split()
    assert {"订单", "自提", "到店"} <= set(terms)


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
    base_id, _ = await _prepare_knowledge_base(client, headers_a)

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
    new_search = await client.post(
        f"/v1/admin/knowledge-bases/{base_id}/search",
        headers=headers_a,
        json={"query": "How many days are allowed for returns?", "top_k": 5},
    )
    assert new_search.status_code == 200, new_search.text
    assert all("30 days" not in item["content"] for item in new_search.json())
    assert "45 days" in new_search.json()[0]["content"]

    replacement_id = replacement.json()["document"]["id"]
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

    still_ready = await client.get(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{replacement_id}",
        headers=headers_a,
    )
    assert still_ready.status_code == 200
    assert still_ready.json()["document"]["status"] == "ready"

    monkeypatch.setattr(memory_storage, "delete", original_delete)
    retried_delete = await client.delete(
        f"/v1/admin/knowledge-bases/{base_id}/documents/{replacement_id}",
        headers=headers_a,
    )
    assert retried_delete.status_code == 204
    assert not any(replacement_id in key for key in memory_storage.objects)


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
