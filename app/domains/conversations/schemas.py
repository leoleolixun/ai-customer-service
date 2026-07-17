from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.conversations.models import (
    ConversationMode,
    ConversationStatus,
    FeedbackRating,
    MessageSender,
    MessageStatus,
)
from app.domains.knowledge.schemas import CitationResponse


class ConversationLocale(StrEnum):
    EN = "en"
    ZH_CN = "zh-CN"


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    mode: ConversationMode
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8_000)
    locale: ConversationLocale = ConversationLocale.EN


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    sender: MessageSender
    content: str
    status: MessageStatus
    error_code: str | None
    citations: list[CitationResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class FeedbackCreate(BaseModel):
    message_id: UUID
    rating: FeedbackRating
    comment: str | None = Field(default=None, max_length=1_000)


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    conversation_id: UUID
    message_id: UUID
    rating: FeedbackRating
    comment: str | None
    created_at: datetime
    updated_at: datetime


class AdminFeedbackResponse(FeedbackResponse):
    message_excerpt: str
