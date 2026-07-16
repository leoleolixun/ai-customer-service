from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StaffStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class TenantRole(StrEnum):
    TENANT_ADMIN = "tenant_admin"
    AGENT = "agent"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class StaffUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "staff_users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[StaffStatus] = mapped_column(
        Enum(
            StaffStatus,
            name="staff_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=StaffStatus.ACTIVE,
        nullable=False,
    )


class TenantMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "staff_user_id"),
        Index("ix_memberships_tenant_role", "tenant_id", "role"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    staff_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[TenantRole] = mapped_column(
        Enum(
            TenantRole,
            name="tenant_role",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        Enum(
            MembershipStatus,
            name="membership_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=MembershipStatus.ACTIVE,
        nullable=False,
    )
