from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from app.domains.model_gateway.models import (
    ModelPurpose,
    ModelStatus,
    ProviderKind,
    ProviderScope,
    ProviderStatus,
)


class ProviderAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: ProviderKind
    base_url: str | None = Field(default=None, max_length=500)
    api_key: SecretStr | None = None

    @model_validator(mode="after")
    def validate_provider_fields(self) -> "ProviderAccountCreate":
        if self.kind == ProviderKind.OPENAI_COMPATIBLE and (
            not self.base_url or self.api_key is None
        ):
            raise ValueError("base_url and api_key are required for OpenAI-compatible providers")
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
    input_price_micros_per_million: int = Field(default=0, ge=0)
    output_price_micros_per_million: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_dimension(self) -> "ModelConfigCreate":
        if self.purpose == ModelPurpose.EMBEDDING and self.embedding_dimension is None:
            raise ValueError("embedding_dimension is required for embedding models")
        if self.purpose == ModelPurpose.CHAT and self.embedding_dimension is not None:
            raise ValueError("embedding_dimension is only valid for embedding models")
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
    input_price_micros_per_million: int
    output_price_micros_per_million: int
    status: ModelStatus
    created_at: datetime
    updated_at: datetime


class ModelActivateRequest(BaseModel):
    application_id: UUID
