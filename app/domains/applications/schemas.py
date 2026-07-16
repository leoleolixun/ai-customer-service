from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.applications.models import ApplicationStatus


def validate_origins(origins: list[str] | None) -> list[str] | None:
    if origins is None:
        return None
    normalized: list[str] = []
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("origins must contain only an http(s) scheme and host")
        normalized.append(f"{parsed.scheme}://{parsed.netloc}")
    return list(dict.fromkeys(normalized))


class ApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    allowed_origins: list[str] = Field(default_factory=list, max_length=20)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10_000)

    _validate_origins = field_validator("allowed_origins")(validate_origins)


class ApplicationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    allowed_origins: list[str] | None = Field(default=None, max_length=20)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=10_000)
    status: ApplicationStatus | None = None

    _validate_origins = field_validator("allowed_origins")(validate_origins)


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    public_key: str
    allowed_origins: list[str]
    rate_limit_per_minute: int
    status: ApplicationStatus
    created_at: datetime
    updated_at: datetime


class CredentialCreate(BaseModel):
    scopes: list[str] = Field(default_factory=lambda: ["customer_token:create"], min_length=1)
    expires_at: datetime | None = None


class CredentialCreatedResponse(BaseModel):
    id: UUID
    key_prefix: str
    api_key: str
    scopes: list[str]
    expires_at: datetime | None
    created_at: datetime


class CredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class CustomerTokenRequest(BaseModel):
    external_user_id: str = Field(min_length=1, max_length=128)


class CustomerTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
