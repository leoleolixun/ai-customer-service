from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UsageSummaryResponse(BaseModel):
    from_at: datetime
    to_at: datetime
    application_id: UUID | None
    total_requests: int
    completed_requests: int
    failed_requests: int
    prompt_tokens: int
    completion_tokens: int
    average_duration_ms: float
    estimated_cost_micros: int


class ModelCallResponse(BaseModel):
    id: UUID
    application_id: UUID
    conversation_id: UUID
    message_id: UUID
    model_config_id: UUID
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    duration_ms: int
    estimated_cost_micros: int
    status: str
    error_code: str | None
    created_at: datetime


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_type: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str | None
    request_id: str | None
    details: dict[str, Any]
    created_at: datetime
