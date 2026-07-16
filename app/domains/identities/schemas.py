from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domains.identities.models import MembershipStatus, TenantRole


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    tenant_id: UUID | None = None


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class AdminMeResponse(BaseModel):
    id: UUID
    email: str
    is_platform_admin: bool
    tenant_id: UUID | None
    role: TenantRole | None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def reject_unchanged_password(self) -> "PasswordChangeRequest":
        if self.current_password == self.new_password:
            raise ValueError("new_password must differ from current_password")
        return self


class MemberCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    temporary_password: str = Field(min_length=12, max_length=128)
    role: TenantRole


class TenantAdminCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    temporary_password: str = Field(min_length=12, max_length=128)


class MemberUpdate(BaseModel):
    role: TenantRole | None = None
    status: MembershipStatus | None = None


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    email: str
    display_name: str
    role: TenantRole
    status: MembershipStatus
    created_at: datetime
