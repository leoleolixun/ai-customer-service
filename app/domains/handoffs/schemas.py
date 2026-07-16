from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.handoffs.models import HandoffStatus


class HandoffCreate(BaseModel):
    reason: str = Field(default="", max_length=1000)


class HandoffClose(BaseModel):
    reason: str = Field(default="resolved", min_length=1, max_length=500)


class HumanMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class HandoffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    conversation_id: UUID
    assigned_staff_user_id: UUID | None
    status: HandoffStatus
    reason: str
    summary: str
    accepted_at: datetime | None
    closed_at: datetime | None
    close_reason: str | None
    created_at: datetime
    updated_at: datetime
