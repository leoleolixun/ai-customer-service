from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identities.models import (
    MembershipStatus,
    StaffUser,
    TenantMembership,
    TenantRole,
)


class IdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_by_email(self, email: str) -> StaffUser | None:
        statement = select(StaffUser).where(func.lower(StaffUser.email) == email.lower())
        return cast(StaffUser | None, await self.session.scalar(statement))

    async def get_user_by_id(self, user_id: UUID) -> StaffUser | None:
        return await self.session.get(StaffUser, user_id)

    async def get_membership(
        self, *, tenant_id: UUID, staff_user_id: UUID
    ) -> TenantMembership | None:
        statement = select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.staff_user_id == staff_user_id,
        )
        return cast(TenantMembership | None, await self.session.scalar(statement))

    async def create_platform_admin(
        self, *, email: str, display_name: str, password_hash: str
    ) -> StaffUser:
        user = StaffUser(
            email=email.lower(),
            display_name=display_name,
            password_hash=password_hash,
            is_platform_admin=True,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def create_staff_user(
        self, *, email: str, display_name: str, password_hash: str
    ) -> StaffUser:
        user = StaffUser(
            email=email.lower(),
            display_name=display_name,
            password_hash=password_hash,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def create_membership(
        self, *, tenant_id: UUID, staff_user_id: UUID, role: TenantRole
    ) -> TenantMembership:
        membership = TenantMembership(
            tenant_id=tenant_id,
            staff_user_id=staff_user_id,
            role=role,
        )
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def list_memberships(self, tenant_id: UUID) -> list[tuple[TenantMembership, StaffUser]]:
        statement = (
            select(TenantMembership, StaffUser)
            .join(StaffUser, StaffUser.id == TenantMembership.staff_user_id)
            .where(TenantMembership.tenant_id == tenant_id)
            .order_by(TenantMembership.created_at, TenantMembership.id)
        )
        result = await self.session.execute(statement)
        return list(result.tuples())

    async def get_membership_with_user(
        self, *, tenant_id: UUID, membership_id: UUID
    ) -> tuple[TenantMembership, StaffUser] | None:
        statement = (
            select(TenantMembership, StaffUser)
            .join(StaffUser, StaffUser.id == TenantMembership.staff_user_id)
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.id == membership_id,
            )
        )
        result = await self.session.execute(statement)
        return result.tuples().one_or_none()

    async def count_active_admins(self, tenant_id: UUID) -> int:
        statement = select(func.count(TenantMembership.id)).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.role == TenantRole.TENANT_ADMIN,
            TenantMembership.status == MembershipStatus.ACTIVE,
        )
        return int(await self.session.scalar(statement) or 0)
