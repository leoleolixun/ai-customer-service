from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProviderScope(StrEnum):
    PLATFORM = "platform"
    TENANT = "tenant"


class ProviderKind(StrEnum):
    FAKE = "fake"
    OPENAI_COMPATIBLE = "openai_compatible"


class ProviderStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    DISABLED = "disabled"


class ModelPurpose(StrEnum):
    CHAT = "chat"
    EMBEDDING = "embedding"


class ModelStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"


class AIProviderAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_provider_accounts"
    __table_args__ = (
        CheckConstraint(
            "(scope = 'platform' AND tenant_id IS NULL) OR "
            "(scope = 'tenant' AND tenant_id IS NOT NULL)",
            name="provider_scope_owner",
        ),
        Index(
            "uq_provider_accounts_platform_name",
            "name",
            unique=True,
            postgresql_where=text("scope = 'platform'"),
            sqlite_where=text("scope = 'platform'"),
        ),
        Index(
            "uq_provider_accounts_tenant_name",
            "tenant_id",
            "name",
            unique=True,
            postgresql_where=text("scope = 'tenant'"),
            sqlite_where=text("scope = 'tenant'"),
        ),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scope: Mapped[ProviderScope] = mapped_column(
        Enum(
            ProviderScope,
            name="provider_scope",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[ProviderKind] = mapped_column(
        Enum(
            ProviderKind,
            name="provider_kind",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProviderStatus] = mapped_column(
        Enum(
            ProviderStatus,
            name="provider_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ProviderStatus.DRAFT,
        nullable=False,
        index=True,
    )


class AIModelConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_model_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),
        Index("ix_ai_model_configs_tenant_purpose", "tenant_id", "purpose"),
        CheckConstraint(
            "(purpose = 'embedding' AND embedding_dimension IS NOT NULL) OR "
            "(purpose = 'chat' AND embedding_dimension IS NULL)",
            name="model_embedding_dimension",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_provider_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[ModelPurpose] = mapped_column(
        Enum(
            ModelPurpose,
            name="model_purpose",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature: Mapped[float] = mapped_column(Float, default=0.2, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    input_price_micros_per_million: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    output_price_micros_per_million: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    status: Mapped[ModelStatus] = mapped_column(
        Enum(
            ModelStatus,
            name="model_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ModelStatus.INACTIVE,
        nullable=False,
    )


class ApplicationModelBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "application_model_bindings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "application_id", "purpose"),
        Index("ix_model_bindings_tenant_app", "tenant_id", "application_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_config_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_model_configs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    purpose: Mapped[ModelPurpose] = mapped_column(
        Enum(
            ModelPurpose,
            name="binding_model_purpose",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
