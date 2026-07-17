from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.domains.model_gateway.models import (
    ModelPurpose,
    ModelStatus,
    ProviderKind,
    ProviderScope,
    ProviderStatus,
    ThinkingMode,
)


def validate_provider_api_key(value: SecretStr | None) -> SecretStr | None:
    if value is None:
        return None
    raw_value = value.get_secret_value()
    if not raw_value or raw_value != raw_value.strip():
        raise ValueError("api_key must not be blank or contain surrounding whitespace")
    if not raw_value.isascii():
        raise ValueError("api_key must contain ASCII characters only")
    if any(character.isspace() for character in raw_value):
        raise ValueError("api_key must not contain whitespace")
    if raw_value.lower().startswith("bearer "):
        raise ValueError("api_key must not include the Bearer prefix")
    return value


class ProviderAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: ProviderKind
    base_url: str | None = Field(default=None, max_length=500)
    api_key: SecretStr | None = Field(
        default=None,
        description="Provider API key using ASCII characters, without a Bearer prefix.",
    )

    _validate_api_key = field_validator("api_key")(validate_provider_api_key)

    @model_validator(mode="after")
    def validate_provider_fields(self) -> "ProviderAccountCreate":
        if self.kind == ProviderKind.OPENAI_COMPATIBLE and (
            not self.base_url or self.api_key is None
        ):
            raise ValueError("base_url and api_key are required for OpenAI-compatible providers")
        return self


class ProviderAccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: SecretStr | None = Field(
        default=None,
        description="Replacement API key using ASCII characters, without a Bearer prefix.",
    )

    _validate_api_key = field_validator("api_key")(validate_provider_api_key)

    @model_validator(mode="after")
    def validate_update_fields(self) -> "ProviderAccountUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one provider field must be supplied")
        for field_name in self.model_fields_set:
            value = getattr(self, field_name)
            if value is None:
                raise ValueError(f"{field_name} cannot be null")
            if isinstance(value, str) and not value.strip():
                raise ValueError(f"{field_name} cannot be blank")
            if isinstance(value, SecretStr) and not value.get_secret_value().strip():
                raise ValueError(f"{field_name} cannot be blank")
        return self


class ProviderAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID | None
    scope: ProviderScope
    name: str
    kind: ProviderKind
    base_url: str | None
    has_api_key: bool
    can_manage: bool
    status: ProviderStatus
    created_at: datetime
    updated_at: datetime


class ProviderTestResponse(BaseModel):
    status: ProviderStatus
    message: str


class ModelConfigCreate(BaseModel):
    provider_account_id: UUID
    name: str = Field(min_length=1, max_length=120)
    model_name: str = Field(min_length=1, max_length=200)
    purpose: ModelPurpose
    embedding_dimension: int | None = Field(default=None, ge=8, le=16_384)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=1024, ge=1, le=128_000)
    thinking_mode: ThinkingMode = ThinkingMode.PROVIDER_DEFAULT
    input_price_micros_per_million: int = Field(default=0, ge=0)
    output_price_micros_per_million: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_dimension(self) -> "ModelConfigCreate":
        if self.purpose == ModelPurpose.EMBEDDING and self.embedding_dimension is None:
            raise ValueError("embedding_dimension is required for embedding models")
        if self.purpose == ModelPurpose.CHAT and self.embedding_dimension is not None:
            raise ValueError("embedding_dimension is only valid for embedding models")
        if (
            self.purpose == ModelPurpose.EMBEDDING
            and self.thinking_mode != ThinkingMode.PROVIDER_DEFAULT
        ):
            raise ValueError("thinking_mode is only configurable for chat models")
        return self


class ModelConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    provider_account_id: UUID
    name: str
    model_name: str
    purpose: ModelPurpose
    embedding_dimension: int | None
    temperature: float
    max_tokens: int
    thinking_mode: ThinkingMode
    input_price_micros_per_million: int
    output_price_micros_per_million: int
    status: ModelStatus
    created_at: datetime
    updated_at: datetime


class ModelActivateRequest(BaseModel):
    application_id: UUID
