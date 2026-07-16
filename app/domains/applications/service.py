import secrets
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import NoReturn
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import (
    CustomerPrincipal,
    StaffPrincipal,
    create_customer_token,
    generate_api_credential,
    hash_api_secret,
    split_api_key,
    verify_api_secret,
)
from app.domains.applications.models import ApiCredential, Application, ApplicationStatus
from app.domains.applications.repository import (
    ApplicationRepository,
    CredentialAuthenticator,
    CredentialRepository,
)
from app.domains.applications.schemas import (
    ApplicationCreate,
    ApplicationUpdate,
    CredentialCreate,
    CredentialCreatedResponse,
    CustomerTokenResponse,
)
from app.domains.audit.repository import AuditRepository
from app.domains.tenants.models import TenantStatus
from app.domains.tenants.repository import TenantRepository


class ApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.applications = ApplicationRepository(session)
        self.credentials = CredentialRepository(session)
        self.audit = AuditRepository(session)

    async def create(
        self,
        *,
        tenant_id: UUID,
        request: ApplicationCreate,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> Application:
        try:
            application = await self.applications.create(
                tenant_id=tenant_id,
                name=request.name.strip(),
                public_key=f"app_{secrets.token_hex(16)}",
                allowed_origins=request.allowed_origins,
                rate_limit_per_minute=request.rate_limit_per_minute,
            )
            await self._audit(actor, application, "application.create", request_id)
            await self.session.commit()
            await self.session.refresh(application)
            return application
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                status_code=409,
                code="application_name_conflict",
                title="Application already exists",
                detail="An application with this name already exists in the tenant.",
            ) from exc

    async def list(self, tenant_id: UUID) -> list[Application]:
        return await self.applications.list_by_tenant(tenant_id)

    async def update(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        request: ApplicationUpdate,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> Application:
        application = await self._get_application(tenant_id, application_id)
        try:
            application = await self.applications.update(
                application,
                name=request.name.strip() if request.name else None,
                allowed_origins=request.allowed_origins,
                rate_limit_per_minute=request.rate_limit_per_minute,
                status=request.status,
            )
            await self._audit(actor, application, "application.update", request_id)
            await self.session.commit()
            await self.session.refresh(application)
            return application
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                status_code=409,
                code="application_name_conflict",
                title="Application already exists",
                detail="An application with this name already exists in the tenant.",
            ) from exc

    async def create_credential(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        request: CredentialCreate,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> CredentialCreatedResponse:
        application = await self._get_application(tenant_id, application_id)
        key_prefix, secret, api_key = generate_api_credential()
        credential = await self.credentials.create(
            tenant_id=tenant_id,
            application_id=application.id,
            key_prefix=key_prefix,
            secret_hash=hash_api_secret(secret),
            scopes=request.scopes,
            expires_at=request.expires_at,
        )
        await self._audit(
            actor,
            application,
            "credential.create",
            request_id,
            resource_id=str(credential.id),
        )
        await self.session.commit()
        await self.session.refresh(credential)
        return CredentialCreatedResponse(
            id=credential.id,
            key_prefix=credential.key_prefix,
            api_key=api_key,
            scopes=credential.scopes,
            expires_at=credential.expires_at,
            created_at=credential.created_at,
        )

    async def list_credentials(
        self, *, tenant_id: UUID, application_id: UUID
    ) -> Sequence[ApiCredential]:
        await self._get_application(tenant_id, application_id)
        return await self.credentials.list_by_application(
            tenant_id=tenant_id, application_id=application_id
        )

    async def revoke_credential(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        credential_id: UUID,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> None:
        application = await self._get_application(tenant_id, application_id)
        credential = await self.credentials.get_by_id(
            tenant_id=tenant_id,
            application_id=application_id,
            credential_id=credential_id,
        )
        if credential is None:
            raise AppError(
                status_code=404,
                code="credential_not_found",
                title="Credential not found",
                detail="The requested credential does not exist.",
            )
        await self.credentials.revoke(credential)
        await self._audit(
            actor,
            application,
            "credential.revoke",
            request_id,
            resource_id=str(credential.id),
        )
        await self.session.commit()

    async def _get_application(self, tenant_id: UUID, application_id: UUID) -> Application:
        application = await self.applications.get_by_id(
            tenant_id=tenant_id, application_id=application_id
        )
        if application is None:
            raise AppError(
                status_code=404,
                code="application_not_found",
                title="Application not found",
                detail="The requested application does not exist in this tenant.",
            )
        return application

    async def _audit(
        self,
        actor: StaffPrincipal,
        application: Application,
        action: str,
        request_id: str | None,
        *,
        resource_id: str | None = None,
    ) -> None:
        await self.audit.add(
            tenant_id=application.tenant_id,
            actor_type="staff",
            actor_id=str(actor.user_id),
            action=action,
            resource_type="application" if resource_id is None else "credential",
            resource_id=resource_id or str(application.id),
            request_id=request_id,
        )


class CustomerTokenService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.authenticator = CredentialAuthenticator(session)
        self.applications = ApplicationRepository(session)
        self.tenants = TenantRepository(session)
        self.audit = AuditRepository(session)

    async def issue(
        self,
        *,
        api_key: str,
        external_user_id: str,
        origin: str | None,
        request_id: str | None,
    ) -> CustomerTokenResponse:
        prefix, secret = split_api_key(api_key)
        credential = await self.authenticator.get_by_prefix(prefix)
        self._validate_credential(credential, secret)
        assert credential is not None
        application = await self.applications.get_by_id(
            tenant_id=credential.tenant_id,
            application_id=credential.application_id,
        )
        tenant = await self.tenants.get_by_id(credential.tenant_id)
        if (
            application is None
            or application.status != ApplicationStatus.ACTIVE
            or tenant is None
            or tenant.status != TenantStatus.ACTIVE
        ):
            self._raise_invalid_api_key()
        if origin is not None and origin not in application.allowed_origins:
            raise AppError(
                status_code=403,
                code="origin_not_allowed",
                title="Origin not allowed",
                detail="This origin is not allowed for the application.",
            )
        principal = CustomerPrincipal(
            tenant_id=credential.tenant_id,
            application_id=credential.application_id,
            external_user_id=external_user_id,
            scopes=("chat:write", "chat:read", "handoff:create"),
            token_id=uuid4(),
        )
        token, expires_at = create_customer_token(principal)
        await self.audit.add(
            tenant_id=credential.tenant_id,
            actor_type="external_user",
            actor_id=external_user_id,
            action="customer_token.issue",
            resource_type="application",
            resource_id=str(credential.application_id),
            request_id=request_id,
            details={"credential_prefix": credential.key_prefix},
        )
        await self.session.commit()
        return CustomerTokenResponse(access_token=token, expires_at=expires_at)

    @staticmethod
    def _validate_credential(credential: ApiCredential | None, secret: str) -> None:
        now = datetime.now(UTC)
        if (
            credential is None
            or credential.revoked_at is not None
            or (credential.expires_at is not None and credential.expires_at <= now)
            or "customer_token:create" not in credential.scopes
            or not verify_api_secret(secret, credential.secret_hash)
        ):
            CustomerTokenService._raise_invalid_api_key()

    @staticmethod
    def _raise_invalid_api_key() -> NoReturn:
        raise AppError(
            status_code=401,
            code="invalid_api_key",
            title="Authentication failed",
            detail="The API key is invalid, expired, or revoked.",
        )
