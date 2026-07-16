from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.tenants.models import Tenant, TenantStatus


class TenantRepository:
    """Platform-only repository; Tenant is the root that establishes tenant context."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, name: str, slug: str) -> Tenant:
        tenant = Tenant(name=name, slug=slug)
        self.session.add(tenant)
        await self.session.flush()
        return tenant

    async def list_all(self) -> list[Tenant]:
        result = await self.session.scalars(select(Tenant).order_by(Tenant.created_at, Tenant.id))
        return list(result)

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        return await self.session.get(Tenant, tenant_id)

    async def update(
        self,
        tenant: Tenant,
        *,
        name: str | None,
        status: TenantStatus | None,
    ) -> Tenant:
        if name is not None:
            tenant.name = name
        if status is not None:
            tenant.status = status
        await self.session.flush()
        return tenant
