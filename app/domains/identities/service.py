from typing import NoReturn
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import (
    StaffPrincipal,
    create_admin_access_token,
    hash_password,
    staff_auth_version,
    verify_password,
)
from app.domains.audit.repository import AuditRepository
from app.domains.identities.models import (
    MembershipStatus,
    StaffStatus,
    StaffUser,
    TenantMembership,
)
from app.domains.identities.repository import IdentityRepository
from app.domains.identities.schemas import (
    AdminLoginRequest,
    AdminTokenResponse,
    MemberCreate,
    MemberResponse,
    MemberUpdate,
    PasswordChangeRequest,
)
from app.domains.tenants.models import TenantStatus
from app.domains.tenants.repository import TenantRepository


class AdminAuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.identities = IdentityRepository(session)
        self.tenants = TenantRepository(session)
        self.audit = AuditRepository(session)

    async def login(self, request: AdminLoginRequest) -> AdminTokenResponse:
        user = await self.identities.get_user_by_email(str(request.email))
        if (
            user is None
            or user.status != StaffStatus.ACTIVE
            or not verify_password(request.password, user.password_hash)
        ):
            self._raise_invalid_credentials()

        principal: StaffPrincipal
        if request.tenant_id is None:
            if not user.is_platform_admin:
                raise AppError(
                    status_code=400,
                    code="tenant_required",
                    title="Tenant required",
                    detail="A tenant_id is required for a tenant account.",
                )
            principal = StaffPrincipal(
                user.id,
                user.email,
                True,
                None,
                None,
                staff_auth_version(user.password_hash),
            )
        else:
            tenant = await self.tenants.get_by_id(request.tenant_id)
            membership = await self.identities.get_membership(
                tenant_id=request.tenant_id, staff_user_id=user.id
            )
            if (
                tenant is None
                or tenant.status != TenantStatus.ACTIVE
                or membership is None
                or membership.status != MembershipStatus.ACTIVE
            ):
                self._raise_invalid_credentials()
            principal = StaffPrincipal(
                user.id,
                user.email,
                user.is_platform_admin,
                request.tenant_id,
                membership.role,
                staff_auth_version(user.password_hash),
            )

        token, expires_at = create_admin_access_token(principal)
        return AdminTokenResponse(access_token=token, expires_at=expires_at)

    async def change_password(
        self,
        *,
        actor: StaffPrincipal,
        request: PasswordChangeRequest,
        request_id: str | None,
    ) -> None:
        user = await self.identities.get_user_by_id(actor.user_id)
        if user is None or not verify_password(request.current_password, user.password_hash):
            raise AppError(
                status_code=400,
                code="current_password_invalid",
                title="Current password invalid",
                detail="The current password is incorrect.",
            )
        user.password_hash = hash_password(request.new_password)
        await self.audit.add(
            tenant_id=actor.tenant_id,
            actor_type="staff",
            actor_id=str(actor.user_id),
            action="auth.password_change",
            resource_type="staff_user",
            resource_id=str(actor.user_id),
            request_id=request_id,
        )
        await self.session.commit()

    @staticmethod
    def _raise_invalid_credentials() -> NoReturn:
        raise AppError(
            status_code=401,
            code="invalid_credentials",
            title="Authentication failed",
            detail="Email, password, or tenant is invalid.",
        )


class MemberService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.identities = IdentityRepository(session)
        self.tenants = TenantRepository(session)
        self.audit = AuditRepository(session)

    async def create(
        self,
        *,
        tenant_id: UUID,
        request: MemberCreate,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> MemberResponse:
        tenant = await self.tenants.get_by_id(tenant_id)
        if tenant is None:
            raise AppError(
                status_code=404,
                code="tenant_not_found",
                title="Tenant not found",
                detail="The requested tenant does not exist.",
            )
        user = await self.identities.get_user_by_email(str(request.email))
        try:
            if user is None:
                user = await self.identities.create_staff_user(
                    email=str(request.email),
                    display_name=request.display_name.strip(),
                    password_hash=hash_password(request.temporary_password),
                )
            existing = await self.identities.get_membership(
                tenant_id=tenant_id, staff_user_id=user.id
            )
            if existing is not None:
                raise AppError(
                    status_code=409,
                    code="membership_conflict",
                    title="Member already exists",
                    detail="This staff user is already a member of the tenant.",
                )
            membership = await self.identities.create_membership(
                tenant_id=tenant_id,
                staff_user_id=user.id,
                role=request.role,
            )
            await self.audit.add(
                tenant_id=tenant_id,
                actor_type="staff",
                actor_id=str(actor.user_id),
                action="member.create",
                resource_type="membership",
                resource_id=str(membership.id),
                request_id=request_id,
                details={"role": membership.role.value},
            )
            await self.session.commit()
            await self.session.refresh(membership)
            return self._to_response(membership, user)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                status_code=409,
                code="membership_conflict",
                title="Member already exists",
                detail="This email or tenant membership already exists.",
            ) from exc

    async def list(self, tenant_id: UUID) -> list[MemberResponse]:
        rows = await self.identities.list_memberships(tenant_id)
        return [self._to_response(membership, user) for membership, user in rows]

    async def update(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        request: MemberUpdate,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> MemberResponse:
        row = await self.identities.get_membership_with_user(
            tenant_id=tenant_id, membership_id=membership_id
        )
        if row is None:
            raise AppError(
                status_code=404,
                code="member_not_found",
                title="Member not found",
                detail="The requested member does not exist in this tenant.",
            )
        membership, user = row
        removes_active_admin = (
            membership.role.value == "tenant_admin"
            and membership.status == MembershipStatus.ACTIVE
            and (
                (request.role is not None and request.role.value != "tenant_admin")
                or request.status == MembershipStatus.DISABLED
            )
        )
        if removes_active_admin and await self.identities.count_active_admins(tenant_id) <= 1:
            raise AppError(
                status_code=409,
                code="last_tenant_admin",
                title="Tenant administrator required",
                detail="The last active tenant administrator cannot be disabled or demoted.",
            )
        if request.role is not None:
            membership.role = request.role
        if request.status is not None:
            membership.status = request.status
        await self.session.flush()
        await self.audit.add(
            tenant_id=tenant_id,
            actor_type="staff",
            actor_id=str(actor.user_id),
            action="member.update",
            resource_type="membership",
            resource_id=str(membership.id),
            request_id=request_id,
            details={"role": membership.role.value, "status": membership.status.value},
        )
        await self.session.commit()
        await self.session.refresh(membership)
        return self._to_response(membership, user)

    @staticmethod
    def _to_response(membership: TenantMembership, user: StaffUser) -> MemberResponse:
        return MemberResponse(
            id=membership.id,
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=membership.role,
            status=membership.status,
            created_at=membership.created_at,
        )
