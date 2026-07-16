from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.errors import AppError
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.core.security import (
    CustomerPrincipal,
    StaffPrincipal,
    decode_token,
    staff_auth_version,
)
from app.core.storage import get_object_storage
from app.domains.applications.models import ApplicationStatus
from app.domains.applications.repository import ApplicationRepository
from app.domains.identities.models import MembershipStatus, StaffStatus, TenantRole
from app.domains.identities.repository import IdentityRepository
from app.domains.tenants.models import TenantStatus
from app.domains.tenants.repository import TenantRepository
from app.providers.storage.base import ObjectStorage

bearer_scheme = HTTPBearer(auto_error=False)
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
StorageDependency = Annotated[ObjectStorage, Depends(get_object_storage)]
RateLimiterDependency = Annotated[RateLimiter, Depends(get_rate_limiter)]


async def get_current_staff(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: SessionDependency,
) -> StaffPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        _raise_unauthenticated()
    payload = decode_token(credentials.credentials, audience="admin")
    try:
        user_id = UUID(str(payload["sub"]))
        tenant_id = UUID(str(payload["tenant_id"])) if payload.get("tenant_id") else None
    except (KeyError, ValueError, TypeError) as exc:
        raise AppError(
            status_code=401,
            code="invalid_token",
            title="Authentication failed",
            detail="The access token contains invalid identity claims.",
        ) from exc

    identities = IdentityRepository(session)
    user = await identities.get_user_by_id(user_id)
    if (
        user is None
        or user.status != StaffStatus.ACTIVE
        or payload.get("auth_version") != staff_auth_version(user.password_hash)
    ):
        _raise_unauthenticated()

    role: TenantRole | None = None
    if tenant_id is not None:
        tenant = await TenantRepository(session).get_by_id(tenant_id)
        membership = await identities.get_membership(tenant_id=tenant_id, staff_user_id=user_id)
        if (
            tenant is None
            or tenant.status != TenantStatus.ACTIVE
            or membership is None
            or membership.status != MembershipStatus.ACTIVE
        ):
            _raise_unauthenticated()
        role = membership.role

    return StaffPrincipal(
        user_id=user.id,
        email=user.email,
        is_platform_admin=user.is_platform_admin,
        tenant_id=tenant_id,
        role=role,
        auth_version=str(payload["auth_version"]),
    )


CurrentStaffDependency = Annotated[StaffPrincipal, Depends(get_current_staff)]


async def require_platform_admin(current: CurrentStaffDependency) -> StaffPrincipal:
    if not current.is_platform_admin or current.tenant_id is not None:
        raise AppError(
            status_code=403,
            code="platform_admin_required",
            title="Forbidden",
            detail="A platform administrator session is required.",
        )
    return current


PlatformAdminDependency = Annotated[StaffPrincipal, Depends(require_platform_admin)]


async def require_tenant_admin(current: CurrentStaffDependency) -> StaffPrincipal:
    if current.tenant_id is None or current.role != TenantRole.TENANT_ADMIN:
        raise AppError(
            status_code=403,
            code="tenant_admin_required",
            title="Forbidden",
            detail="A tenant administrator session is required.",
        )
    return current


TenantAdminDependency = Annotated[StaffPrincipal, Depends(require_tenant_admin)]


async def require_agent(current: CurrentStaffDependency) -> StaffPrincipal:
    if current.tenant_id is None or current.role not in {TenantRole.TENANT_ADMIN, TenantRole.AGENT}:
        raise AppError(
            status_code=403,
            code="agent_required",
            title="Forbidden",
            detail="An active tenant agent session is required.",
        )
    return current


AgentDependency = Annotated[StaffPrincipal, Depends(require_agent)]


async def require_ai_manager(current: CurrentStaffDependency) -> StaffPrincipal:
    is_platform_manager = current.is_platform_admin and current.tenant_id is None
    is_tenant_manager = current.tenant_id is not None and current.role == TenantRole.TENANT_ADMIN
    if not is_platform_manager and not is_tenant_manager:
        raise AppError(
            status_code=403,
            code="ai_manager_required",
            title="Forbidden",
            detail="A platform or tenant AI administrator session is required.",
        )
    return current


AIManagerDependency = Annotated[StaffPrincipal, Depends(require_ai_manager)]


async def get_current_customer(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: SessionDependency,
    rate_limiter: RateLimiterDependency,
    origin: Annotated[str | None, Header(alias="Origin")] = None,
) -> CustomerPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        _raise_unauthenticated()
    payload = decode_token(credentials.credentials, audience="customer")
    try:
        tenant_id = UUID(str(payload["tenant_id"]))
        application_id = UUID(str(payload["application_id"]))
        token_id = UUID(str(payload["jti"]))
        external_user_id = str(payload["sub"])
        scopes = tuple(str(scope) for scope in payload.get("scopes", []))
    except (KeyError, ValueError, TypeError) as exc:
        raise AppError(
            status_code=401,
            code="invalid_token",
            title="Authentication failed",
            detail="The customer token contains invalid identity claims.",
        ) from exc

    tenant = await TenantRepository(session).get_by_id(tenant_id)
    application = await ApplicationRepository(session).get_by_id(
        tenant_id=tenant_id, application_id=application_id
    )
    if (
        tenant is None
        or tenant.status != TenantStatus.ACTIVE
        or application is None
        or application.status != ApplicationStatus.ACTIVE
    ):
        _raise_unauthenticated()
    if origin is not None and origin not in application.allowed_origins:
        raise AppError(
            status_code=403,
            code="origin_not_allowed",
            title="Origin not allowed",
            detail="This origin is not allowed for the application.",
        )
    if request.method != "GET":
        await rate_limiter.check(
            tenant_id=tenant_id,
            application_id=application_id,
            subject=external_user_id,
            limit=application.rate_limit_per_minute,
        )
    return CustomerPrincipal(
        tenant_id=tenant_id,
        application_id=application_id,
        external_user_id=external_user_id,
        scopes=scopes,
        token_id=token_id,
    )


CurrentCustomerDependency = Annotated[CustomerPrincipal, Depends(get_current_customer)]


def _raise_unauthenticated() -> NoReturn:
    raise AppError(
        status_code=401,
        code="authentication_required",
        title="Authentication required",
        detail="A valid access token is required.",
    )
