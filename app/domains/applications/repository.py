from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.applications.models import ApiCredential, Application, ApplicationStatus


class ApplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        name: str,
        public_key: str,
        allowed_origins: list[str],
        rate_limit_per_minute: int,
    ) -> Application:
        application = Application(
            tenant_id=tenant_id,
            name=name,
            public_key=public_key,
            allowed_origins=allowed_origins,
            rate_limit_per_minute=rate_limit_per_minute,
        )
        self.session.add(application)
        await self.session.flush()
        return application

    async def list_by_tenant(self, tenant_id: UUID) -> list[Application]:
        statement = (
            select(Application)
            .where(Application.tenant_id == tenant_id)
            .order_by(Application.created_at, Application.id)
        )
        return list(await self.session.scalars(statement))

    async def get_by_id(self, *, tenant_id: UUID, application_id: UUID) -> Application | None:
        statement = select(Application).where(
            Application.id == application_id,
            Application.tenant_id == tenant_id,
        )
        return cast(Application | None, await self.session.scalar(statement))

    async def update(
        self,
        application: Application,
        *,
        name: str | None,
        allowed_origins: list[str] | None,
        rate_limit_per_minute: int | None,
        status: ApplicationStatus | None,
    ) -> Application:
        if name is not None:
            application.name = name
        if allowed_origins is not None:
            application.allowed_origins = allowed_origins
        if rate_limit_per_minute is not None:
            application.rate_limit_per_minute = rate_limit_per_minute
        if status is not None:
            application.status = status
        await self.session.flush()
        return application


class CredentialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        key_prefix: str,
        secret_hash: str,
        scopes: list[str],
        expires_at: datetime | None,
    ) -> ApiCredential:
        credential = ApiCredential(
            tenant_id=tenant_id,
            application_id=application_id,
            key_prefix=key_prefix,
            secret_hash=secret_hash,
            scopes=scopes,
            expires_at=expires_at,
        )
        self.session.add(credential)
        await self.session.flush()
        return credential

    async def get_by_id(
        self, *, tenant_id: UUID, application_id: UUID, credential_id: UUID
    ) -> ApiCredential | None:
        statement = select(ApiCredential).where(
            ApiCredential.id == credential_id,
            ApiCredential.tenant_id == tenant_id,
            ApiCredential.application_id == application_id,
        )
        return cast(ApiCredential | None, await self.session.scalar(statement))

    async def list_by_application(
        self, *, tenant_id: UUID, application_id: UUID
    ) -> list[ApiCredential]:
        statement = (
            select(ApiCredential)
            .where(
                ApiCredential.tenant_id == tenant_id,
                ApiCredential.application_id == application_id,
            )
            .order_by(ApiCredential.created_at.desc(), ApiCredential.id.desc())
        )
        return list(await self.session.scalars(statement))

    async def revoke(self, credential: ApiCredential) -> None:
        credential.revoked_at = datetime.now(UTC)
        await self.session.flush()


class CredentialAuthenticator:
    """Authentication boundary: resolves tenant context from a globally unique key prefix."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_prefix(self, key_prefix: str) -> ApiCredential | None:
        return cast(
            ApiCredential | None,
            await self.session.scalar(
                select(ApiCredential).where(ApiCredential.key_prefix == key_prefix)
            ),
        )
