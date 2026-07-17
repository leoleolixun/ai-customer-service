from datetime import datetime
from enum import StrEnum
from typing import Any
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


class AdminConversationResponse(BaseModel):
    id: UUID
    application_id: UUID
    end_user_id: UUID
    external_user_id: str
    mode: ConversationMode
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime


class AdminConversationPage(BaseModel):
    items: list[AdminConversationResponse]
    next_cursor: UUID | None = None
    has_more: bool


class AdminMessageResponse(MessageResponse):
    model_info: dict[str, Any] = Field(default_factory=dict)


class AdminMessagePage(BaseModel):
    items: list[AdminMessageResponse]
    next_cursor: UUID | None = None
    has_more: bool


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
