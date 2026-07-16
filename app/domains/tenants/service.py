from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import StaffPrincipal
from app.domains.audit.repository import AuditRepository
from app.domains.tenants.models import Tenant
from app.domains.tenants.repository import TenantRepository
from app.domains.tenants.schemas import TenantCreate, TenantUpdate


class TenantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tenants = TenantRepository(session)
        self.audit = AuditRepository(session)

    async def create(
        self, request: TenantCreate, actor: StaffPrincipal, request_id: str | None
    ) -> Tenant:
        try:
            tenant = await self.tenants.create(name=request.name.strip(), slug=request.slug)
            await self.audit.add(
                tenant_id=tenant.id,
                actor_type="staff",
                actor_id=str(actor.user_id),
                action="tenant.create",
                resource_type="tenant",
                resource_id=str(tenant.id),
                request_id=request_id,
            )
            await self.session.commit()
            await self.session.refresh(tenant)
            return tenant
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                status_code=409,
                code="tenant_slug_conflict",
                title="Tenant already exists",
                detail="A tenant with this slug already exists.",
            ) from exc

    async def list_all(self) -> list[Tenant]:
        return await self.tenants.list_all()

    async def update(
        self,
        tenant_id: UUID,
        request: TenantUpdate,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> Tenant:
        tenant = await self.tenants.get_by_id(tenant_id)
        if tenant is None:
            raise AppError(
                status_code=404,
                code="tenant_not_found",
                title="Tenant not found",
                detail="The requested tenant does not exist.",
            )
        tenant = await self.tenants.update(
            tenant,
            name=request.name.strip() if request.name else None,
            status=request.status,
        )
        await self.audit.add(
            tenant_id=tenant.id,
            actor_type="staff",
            actor_id=str(actor.user_id),
            action="tenant.update",
            resource_type="tenant",
            resource_id=str(tenant.id),
            request_id=request_id,
            details={"status": tenant.status.value},
        )
        await self.session.commit()
        await self.session.refresh(tenant)
        return tenant
