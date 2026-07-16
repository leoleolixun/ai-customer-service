from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ConversationMode(StrEnum):
    AI = "ai"
    HUMAN = "human"


class ConversationStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class MessageSender(StrEnum):
    USER = "user"
    AI = "ai"
    AGENT = "agent"
    SYSTEM = "system"


class MessageStatus(StrEnum):
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class FeedbackRating(StrEnum):
    HELPFUL = "helpful"
    UNHELPFUL = "unhelpful"


class EndUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "end_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "application_id", "external_user_id"),
        Index("ix_end_users_tenant_application", "tenant_id", "application_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_tenant_application", "tenant_id", "application_id"),
        Index("ix_conversations_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    end_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("end_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[ConversationMode] = mapped_column(
        Enum(
            ConversationMode,
            name="conversation_mode",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ConversationMode.AI,
        nullable=False,
    )
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(
            ConversationStatus,
            name="conversation_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ConversationStatus.OPEN,
        nullable=False,
    )


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "conversation_id", "idempotency_key"),
        Index(
            "ix_messages_tenant_conversation_created", "tenant_id", "conversation_id", "created_at"
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
    reply_to_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sender: Mapped[MessageSender] = mapped_column(
        Enum(
            MessageSender,
            name="message_sender",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    sender_staff_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[MessageStatus] = mapped_column(
        Enum(
            MessageStatus,
            name="message_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_config_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ai_model_configs.id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_info: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ConversationFeedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_feedback"
    __table_args__ = (
        UniqueConstraint("tenant_id", "message_id"),
        Index("ix_feedback_tenant_created", "tenant_id", "created_at"),
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
    end_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("end_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rating: Mapped[FeedbackRating] = mapped_column(
        Enum(
            FeedbackRating,
            name="feedback_rating",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
