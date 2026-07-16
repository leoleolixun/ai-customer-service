from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class HandoffStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class HandoffRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "handoff_requests"
    __table_args__ = (
        Index("ix_handoffs_tenant_status_created", "tenant_id", "status", "created_at"),
        Index(
            "uq_handoffs_active_conversation",
            "tenant_id",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'accepted')"),
            sqlite_where=text("status IN ('pending', 'accepted')"),
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by_end_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("end_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_staff_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    closed_by_staff_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[HandoffStatus] = mapped_column(
        Enum(
            HandoffStatus,
            name="handoff_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=HandoffStatus.PENDING,
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
