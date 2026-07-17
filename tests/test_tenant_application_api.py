from collections.abc import Mapping
from typing import Any

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.domains.audit.models import AuditLog
from app.domains.identities.models import StaffUser, TenantMembership, TenantRole
from app.domains.tenants.models import Tenant


async def create_staff_fixtures(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Tenant, Tenant]:
    async with session_factory() as session:
        tenant_a = Tenant(name="Tenant A", slug="tenant-a")
        tenant_b = Tenant(name="Tenant B", slug="tenant-b")
        platform = StaffUser(
            email="platform@example.com",
            display_name="Platform Admin",
            password_hash=hash_password("platform-password"),
            is_platform_admin=True,
        )
        tenant_admin = StaffUser(
            email="admin@example.com",
            display_name="Tenant Admin",
            password_hash=hash_password("tenant-password"),
        )
        session.add_all([tenant_a, tenant_b, platform, tenant_admin])
        await session.flush()
        session.add_all(
            [
                TenantMembership(
                    tenant_id=tenant_a.id,
                    staff_user_id=tenant_admin.id,
                    role=TenantRole.TENANT_ADMIN,
                ),
                TenantMembership(
                    tenant_id=tenant_b.id,
                    staff_user_id=tenant_admin.id,
                    role=TenantRole.TENANT_ADMIN,
                ),
            ]
        )
        await session.commit()
        return tenant_a, tenant_b


async def login(client: AsyncClient, body: Mapping[str, Any]) -> str:
    response = await client.post("/v1/admin/auth/login", json=dict(body))
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


async def test_platform_tenant_management_uses_problem_details(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await create_staff_fixtures(session_factory)
    token = await login(
        client,
        {"email": "platform@example.com", "password": "platform-password"},
    )
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/v1/platform/tenants",
        headers=headers,
        json={"name": "Third tenant", "slug": "tenant-c"},
    )
    assert response.status_code == 201
    tenant_id = response.json()["id"]

    created_admin = await client.post(
        f"/v1/platform/tenants/{tenant_id}/admins",
        headers=headers,
        json={
            "email": "tenant-c-admin@example.com",
            "display_name": "Tenant C Admin",
            "temporary_password": "tenant-c-password",
        },
    )
    assert created_admin.status_code == 201, created_admin.text
    assert created_admin.json()["role"] == "tenant_admin"

    tenant_login = await client.post(
        "/v1/admin/auth/login",
        json={
            "email": "tenant-c-admin@example.com",
            "password": "tenant-c-password",
            "tenant_id": tenant_id,
        },
    )
    assert tenant_login.status_code == 200, tenant_login.text

    duplicate = await client.post(
        "/v1/platform/tenants",
        headers=headers,
        json={"name": "Duplicate", "slug": "tenant-c"},
    )
    assert duplicate.status_code == 409
    assert duplicate.headers["content-type"].startswith("application/problem+json")
    assert duplicate.json()["code"] == "tenant_slug_conflict"
    assert duplicate.json()["request_id"]


async def test_staff_can_change_password_and_old_password_stops_working(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant, _ = await create_staff_fixtures(session_factory)
    token = await login(
        client,
        {
            "email": "admin@example.com",
            "password": "tenant-password",
            "tenant_id": str(tenant.id),
        },
    )
    headers = {"Authorization": f"Bearer {token}"}

    incorrect = await client.post(
        "/v1/admin/auth/change-password",
        headers=headers,
        json={
            "current_password": "wrong-password",
            "new_password": "new-secure-password",
        },
    )
    assert incorrect.status_code == 400
    assert incorrect.json()["code"] == "current_password_invalid"

    changed = await client.post(
        "/v1/admin/auth/change-password",
        headers=headers,
        json={
            "current_password": "tenant-password",
            "new_password": "new-secure-password",
        },
    )
    assert changed.status_code == 204

    old_session = await client.get("/v1/admin/me", headers=headers)
    assert old_session.status_code == 401

    old_login = await client.post(
        "/v1/admin/auth/login",
        json={
            "email": "admin@example.com",
            "password": "tenant-password",
            "tenant_id": str(tenant.id),
        },
    )
    new_login = await client.post(
        "/v1/admin/auth/login",
        json={
            "email": "admin@example.com",
            "password": "new-secure-password",
            "tenant_id": str(tenant.id),
        },
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200

    async with session_factory() as session:
        audit_count = await session.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.tenant_id == tenant.id,
                AuditLog.action == "auth.password_change",
            )
        )
    assert audit_count == 1


async def test_application_and_credentials_are_tenant_isolated(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a, tenant_b = await create_staff_fixtures(session_factory)
    token_a = await login(
        client,
        {
            "email": "admin@example.com",
            "password": "tenant-password",
            "tenant_id": str(tenant_a.id),
        },
    )
    token_b = await login(
        client,
        {
            "email": "admin@example.com",
            "password": "tenant-password",
            "tenant_id": str(tenant_b.id),
        },
    )

    app_a = await client.post(
        "/v1/admin/applications",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Storefront", "allowed_origins": ["https://a.example.com"]},
    )
    app_b = await client.post(
        "/v1/admin/applications",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Storefront", "allowed_origins": ["https://b.example.com"]},
    )
    assert app_a.status_code == 201, app_a.text
    assert app_b.status_code == 201, app_b.text

    second_app_a = await client.post(
        "/v1/admin/applications",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Account portal"},
    )
    assert second_app_a.status_code == 201, second_app_a.text
    duplicate_rename = await client.patch(
        f"/v1/admin/applications/{second_app_a.json()['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Storefront"},
    )
    assert duplicate_rename.status_code == 409
    assert duplicate_rename.json()["code"] == "application_name_conflict"

    cross_tenant_update = await client.patch(
        f"/v1/admin/applications/{app_b.json()['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Compromised"},
    )
    assert cross_tenant_update.status_code == 404

    credential = await client.post(
        f"/v1/admin/applications/{app_a.json()['id']}/credentials",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"scopes": ["customer_token:create"]},
    )
    assert credential.status_code == 201, credential.text
    api_key = credential.json()["api_key"]
    assert api_key.startswith("acs_")

    credential_list = await client.get(
        f"/v1/admin/applications/{app_a.json()['id']}/credentials",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert credential_list.status_code == 200, credential_list.text
    assert credential_list.json()[0]["key_prefix"] == credential.json()["key_prefix"]
    assert "api_key" not in credential_list.json()[0]
    cross_tenant_credentials = await client.get(
        f"/v1/admin/applications/{app_a.json()['id']}/credentials",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_tenant_credentials.status_code == 404

    customer_token = await client.post(
        "/v1/customer-tokens",
        headers={"X-API-Key": api_key, "Origin": "https://a.example.com"},
        json={"external_user_id": "user-123"},
    )
    assert customer_token.status_code == 200, customer_token.text
    claims = jwt.decode(
        customer_token.json()["access_token"],
        get_settings().jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience="customer",
        issuer="ai-customer-service",
    )
    assert claims["tenant_id"] == str(tenant_a.id)
    assert claims["application_id"] == app_a.json()["id"]
    assert claims["sub"] == "user-123"

    wrong_origin = await client.post(
        "/v1/customer-tokens",
        headers={"X-API-Key": api_key, "Origin": "https://evil.example.com"},
        json={"external_user_id": "user-123"},
    )
    assert wrong_origin.status_code == 403

    revoked = await client.delete(
        f"/v1/admin/applications/{app_a.json()['id']}/credentials/{credential.json()['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert revoked.status_code == 204

    rejected = await client.post(
        "/v1/customer-tokens",
        headers={"X-API-Key": api_key, "Origin": "https://a.example.com"},
        json={"external_user_id": "user-123"},
    )
    assert rejected.status_code == 401


async def test_fake_model_configuration_can_be_tested_and_activated(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a, tenant_b = await create_staff_fixtures(session_factory)
    token_a = await login(
        client,
        {
            "email": "admin@example.com",
            "password": "tenant-password",
            "tenant_id": str(tenant_a.id),
        },
    )
    token_b = await login(
        client,
        {
            "email": "admin@example.com",
            "password": "tenant-password",
            "tenant_id": str(tenant_b.id),
        },
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    application = await client.post(
        "/v1/admin/applications",
        headers=headers_a,
        json={"name": "Chat application"},
    )
    assert application.status_code == 201, application.text

    account = await client.post(
        "/v1/admin/ai/provider-accounts",
        headers=headers_a,
        json={"name": "Deterministic CI", "kind": "fake"},
    )
    assert account.status_code == 201, account.text
    assert account.json()["has_api_key"] is False

    tested = await client.post(
        f"/v1/admin/ai/provider-accounts/{account.json()['id']}/test",
        headers=headers_a,
    )
    assert tested.status_code == 200, tested.text
    assert tested.json()["status"] == "ready"

    cross_tenant = await client.post(
        "/v1/admin/ai/model-configs",
        headers=headers_b,
        json={
            "provider_account_id": account.json()["id"],
            "name": "Stolen model",
            "model_name": "fake-chat",
            "purpose": "chat",
        },
    )
    assert cross_tenant.status_code == 400

    model_config = await client.post(
        "/v1/admin/ai/model-configs",
        headers=headers_a,
        json={
            "provider_account_id": account.json()["id"],
            "name": "Primary chat",
            "model_name": "fake-chat",
            "purpose": "chat",
        },
    )
    assert model_config.status_code == 201, model_config.text
    assert model_config.json()["status"] == "inactive"

    activated = await client.post(
        f"/v1/admin/ai/model-configs/{model_config.json()['id']}/activate",
        headers=headers_a,
        json={"application_id": application.json()["id"]},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"

    deactivated = await client.post(
        f"/v1/admin/ai/model-configs/{model_config.json()['id']}/deactivate",
        headers=headers_a,
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["status"] == "inactive"

    in_use = await client.delete(
        f"/v1/admin/ai/provider-accounts/{account.json()['id']}",
        headers=headers_a,
    )
    assert in_use.status_code == 409
    assert in_use.json()["code"] == "provider_account_in_use"


async def test_provider_account_can_be_updated_and_deleted_without_exposing_secret(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_a, tenant_b = await create_staff_fixtures(session_factory)
    token_a = await login(
        client,
        {
            "email": "admin@example.com",
            "password": "tenant-password",
            "tenant_id": str(tenant_a.id),
        },
    )
    token_b = await login(
        client,
        {
            "email": "admin@example.com",
            "password": "tenant-password",
            "tenant_id": str(tenant_b.id),
        },
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    async def accept_provider_url(url: str) -> str:
        return url.rstrip("/")

    monkeypatch.setattr(
        "app.domains.model_gateway.service.validate_external_http_url",
        accept_provider_url,
    )
    created = await client.post(
        "/v1/admin/ai/provider-accounts",
        headers=headers_a,
        json={
            "name": "GLM",
            "kind": "openai_compatible",
            "base_url": "https://old-provider.example.com/v1",
            "api_key": "old-secret",
        },
    )
    assert created.status_code == 201, created.text
    account_id = created.json()["id"]
    assert created.json()["can_manage"] is True
    assert created.json()["has_api_key"] is True
    assert "api_key" not in created.json()

    invalid_key = await client.patch(
        f"/v1/admin/ai/provider-accounts/{account_id}",
        headers=headers_a,
        json={"api_key": "请填写你的 API Key"},
    )
    assert invalid_key.status_code == 422

    updated = await client.patch(
        f"/v1/admin/ai/provider-accounts/{account_id}",
        headers=headers_a,
        json={
            "name": "GLM production",
            "base_url": "https://open.bigmodel.cn/api/paas/v4/",
            "api_key": "replacement-secret",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "GLM production"
    assert updated.json()["base_url"] == "https://open.bigmodel.cn/api/paas/v4"
    assert updated.json()["status"] == "draft"
    assert "replacement-secret" not in updated.text

    cross_tenant_update = await client.patch(
        f"/v1/admin/ai/provider-accounts/{account_id}",
        headers=headers_b,
        json={"name": "stolen"},
    )
    cross_tenant_delete = await client.delete(
        f"/v1/admin/ai/provider-accounts/{account_id}",
        headers=headers_b,
    )
    assert cross_tenant_update.status_code == 404
    assert cross_tenant_delete.status_code == 404

    deleted = await client.delete(
        f"/v1/admin/ai/provider-accounts/{account_id}",
        headers=headers_a,
    )
    assert deleted.status_code == 204

    accounts = await client.get("/v1/admin/ai/provider-accounts", headers=headers_a)
    assert accounts.status_code == 200
    assert all(account["id"] != account_id for account in accounts.json())
