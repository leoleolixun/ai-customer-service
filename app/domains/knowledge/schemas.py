from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.knowledge.models import (
    DocumentStatus,
    IngestionStatus,
    KnowledgeBaseStatus,
)


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4_000)
    embedding_model_config_id: UUID
    embedding_version: str = Field(default="v1", min_length=1, max_length=64)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4_000)
    status: KnowledgeBaseStatus | None = None


class KnowledgeBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    description: str
    embedding_model_config_id: UUID
    embedding_model_name: str
    embedding_dimension: int
    embedding_version: str
    chunking_version: str
    status: KnowledgeBaseStatus
    created_at: datetime
    updated_at: datetime


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    knowledge_base_id: UUID
    supersedes_document_id: UUID | None
    version: int
    title: str
    source_filename: str
    source_url: str | None
    mime_type: str
    byte_size: int
    content_hash: str
    status: DocumentStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    status: IngestionStatus
    stage: str
    attempts: int
    error_message: str | None
    updated_at: datetime


class DocumentAcceptedResponse(BaseModel):
    document: DocumentResponse
    job: IngestionJobResponse


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResultResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    source_url: str | None
    content: str
    heading_path: list[str]
    score: float
    vector_similarity: float
    keyword_score: float


class CitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    chunk_id: UUID
    quote: str
    source_title: str
    source_url: str | None
    score: float
