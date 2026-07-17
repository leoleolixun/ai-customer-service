import math
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.applications.models import Application
from app.domains.conversations.models import Message
from app.domains.knowledge.models import (
    ChunkStatus,
    Citation,
    DocumentStatus,
    IngestionJob,
    IngestionStatus,
    KnowledgeBase,
    KnowledgeBaseBinding,
    KnowledgeBaseStatus,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.domains.knowledge.parsing import ChunkDraft
from app.domains.model_gateway.models import AIModelConfig, AIProviderAccount, ProviderStatus
from app.domains.tenants.models import Tenant


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk: KnowledgeChunk
    document: KnowledgeDocument
    score: float
    vector_similarity: float
    keyword_score: float
    keyword_score_threshold: float = 0.15
    vector_similarity_threshold: float = 0.72


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_base(
        self,
        *,
        tenant_id: UUID,
        name: str,
        description: str,
        model_config: AIModelConfig,
        embedding_version: str,
        keyword_score_threshold: float,
        vector_similarity_threshold: float,
    ) -> KnowledgeBase:
        assert model_config.embedding_dimension is not None
        knowledge_base = KnowledgeBase(
            tenant_id=tenant_id,
            name=name,
            description=description,
            embedding_model_config_id=model_config.id,
            embedding_model_name=model_config.model_name,
            embedding_dimension=model_config.embedding_dimension,
            embedding_version=embedding_version,
            keyword_score_threshold=keyword_score_threshold,
            vector_similarity_threshold=vector_similarity_threshold,
        )
        self.session.add(knowledge_base)
        await self.session.flush()
        return knowledge_base

    async def list_bases(self, tenant_id: UUID) -> list[KnowledgeBase]:
        statement = (
            select(KnowledgeBase)
            .where(KnowledgeBase.tenant_id == tenant_id)
            .order_by(KnowledgeBase.created_at, KnowledgeBase.id)
        )
        return list(await self.session.scalars(statement))

    async def get_base(self, *, tenant_id: UUID, base_id: UUID) -> KnowledgeBase | None:
        statement = select(KnowledgeBase).where(
            KnowledgeBase.id == base_id,
            KnowledgeBase.tenant_id == tenant_id,
        )
        return cast(KnowledgeBase | None, await self.session.scalar(statement))

    async def list_bound_bases(
        self, *, tenant_id: UUID, application_id: UUID
    ) -> list[KnowledgeBase]:
        statement = (
            select(KnowledgeBase)
            .join(
                KnowledgeBaseBinding,
                KnowledgeBaseBinding.knowledge_base_id == KnowledgeBase.id,
            )
            .where(
                KnowledgeBaseBinding.tenant_id == tenant_id,
                KnowledgeBaseBinding.application_id == application_id,
                KnowledgeBase.tenant_id == tenant_id,
                KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE,
            )
            .order_by(KnowledgeBase.id)
        )
        return list(await self.session.scalars(statement))

    async def list_bound_applications(self, *, tenant_id: UUID, base_id: UUID) -> list[Application]:
        statement = (
            select(Application)
            .join(
                KnowledgeBaseBinding,
                KnowledgeBaseBinding.application_id == Application.id,
            )
            .where(
                KnowledgeBaseBinding.tenant_id == tenant_id,
                KnowledgeBaseBinding.knowledge_base_id == base_id,
                Application.tenant_id == tenant_id,
            )
            .order_by(Application.name, Application.id)
        )
        return list(await self.session.scalars(statement))

    async def bind(
        self, *, tenant_id: UUID, application_id: UUID, base_id: UUID
    ) -> KnowledgeBaseBinding:
        statement = select(KnowledgeBaseBinding).where(
            KnowledgeBaseBinding.tenant_id == tenant_id,
            KnowledgeBaseBinding.application_id == application_id,
            KnowledgeBaseBinding.knowledge_base_id == base_id,
        )
        binding = cast(KnowledgeBaseBinding | None, await self.session.scalar(statement))
        if binding is None:
            binding = KnowledgeBaseBinding(
                tenant_id=tenant_id,
                application_id=application_id,
                knowledge_base_id=base_id,
            )
            self.session.add(binding)
            await self.session.flush()
        return binding

    async def unbind(self, *, tenant_id: UUID, application_id: UUID, base_id: UUID) -> None:
        await self.session.execute(
            delete(KnowledgeBaseBinding).where(
                KnowledgeBaseBinding.tenant_id == tenant_id,
                KnowledgeBaseBinding.application_id == application_id,
                KnowledgeBaseBinding.knowledge_base_id == base_id,
            )
        )

    async def create_document(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
        base_id: UUID,
        supersedes: KnowledgeDocument | None,
        title: str,
        filename: str,
        source_url: str | None,
        mime_type: str,
        byte_size: int,
        object_key: str,
        content_hash: str,
    ) -> tuple[KnowledgeDocument, IngestionJob]:
        document = KnowledgeDocument(
            id=document_id,
            tenant_id=tenant_id,
            knowledge_base_id=base_id,
            supersedes_document_id=supersedes.id if supersedes else None,
            version=(supersedes.version + 1) if supersedes else 1,
            title=title,
            source_filename=filename,
            source_url=source_url,
            mime_type=mime_type,
            byte_size=byte_size,
            object_key=object_key,
            content_hash=content_hash,
        )
        self.session.add(document)
        await self.session.flush()
        job = IngestionJob(
            tenant_id=tenant_id,
            knowledge_base_id=base_id,
            document_id=document.id,
        )
        self.session.add(job)
        await self.session.flush()
        return document, job

    async def lock_tenant(self, tenant_id: UUID) -> bool:
        statement = select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
        return await self.session.scalar(statement) is not None

    async def tenant_document_usage(self, tenant_id: UUID) -> tuple[int, int]:
        statement = select(
            func.count(KnowledgeDocument.id),
            func.coalesce(func.sum(KnowledgeDocument.byte_size), 0),
        ).where(
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.status != DocumentStatus.DELETED,
        )
        row = (await self.session.execute(statement)).one()
        return int(row[0]), int(row[1])

    async def find_duplicate_content(
        self, *, tenant_id: UUID, base_id: UUID, content_hash: str
    ) -> KnowledgeDocument | None:
        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.knowledge_base_id == base_id,
            KnowledgeDocument.content_hash == content_hash,
            KnowledgeDocument.status.in_(
                [
                    DocumentStatus.UPLOADED,
                    DocumentStatus.PROCESSING,
                    DocumentStatus.READY,
                    DocumentStatus.FAILED,
                ]
            ),
        )
        return cast(KnowledgeDocument | None, await self.session.scalar(statement))

    async def list_documents(self, *, tenant_id: UUID, base_id: UUID) -> list[KnowledgeDocument]:
        statement = (
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.knowledge_base_id == base_id,
                KnowledgeDocument.status != DocumentStatus.DELETED,
            )
            .order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc())
        )
        return list(await self.session.scalars(statement))

    async def get_document(
        self, *, tenant_id: UUID, base_id: UUID, document_id: UUID
    ) -> KnowledgeDocument | None:
        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.knowledge_base_id == base_id,
        )
        return cast(KnowledgeDocument | None, await self.session.scalar(statement))

    async def get_document_for_update(
        self, *, tenant_id: UUID, base_id: UUID, document_id: UUID
    ) -> KnowledgeDocument | None:
        statement = (
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.knowledge_base_id == base_id,
            )
            .with_for_update()
        )
        return cast(KnowledgeDocument | None, await self.session.scalar(statement))

    async def get_job(self, *, tenant_id: UUID, document_id: UUID) -> IngestionJob | None:
        statement = select(IngestionJob).where(
            IngestionJob.tenant_id == tenant_id,
            IngestionJob.document_id == document_id,
        )
        return cast(IngestionJob | None, await self.session.scalar(statement))

    async def get_ingestion_context(
        self, *, tenant_id: UUID, document_id: UUID
    ) -> (
        tuple[
            KnowledgeDocument,
            KnowledgeBase,
            IngestionJob,
            AIModelConfig,
            AIProviderAccount,
        ]
        | None
    ):
        statement = (
            select(
                KnowledgeDocument,
                KnowledgeBase,
                IngestionJob,
                AIModelConfig,
                AIProviderAccount,
            )
            .join(KnowledgeBase, KnowledgeBase.id == KnowledgeDocument.knowledge_base_id)
            .join(IngestionJob, IngestionJob.document_id == KnowledgeDocument.id)
            .join(
                AIModelConfig,
                AIModelConfig.id == KnowledgeBase.embedding_model_config_id,
            )
            .join(
                AIProviderAccount,
                AIProviderAccount.id == AIModelConfig.provider_account_id,
            )
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.status != DocumentStatus.DELETED,
                KnowledgeBase.tenant_id == tenant_id,
                IngestionJob.tenant_id == tenant_id,
                AIModelConfig.tenant_id == tenant_id,
                AIProviderAccount.status == ProviderStatus.READY,
            )
            .with_for_update(of=KnowledgeDocument)
        )
        result = await self.session.execute(statement)
        return result.tuples().one_or_none()

    async def prepare_retry(self, document: KnowledgeDocument, job: IngestionJob) -> None:
        document.status = DocumentStatus.UPLOADED
        document.error_message = None
        job.status = IngestionStatus.PENDING
        job.stage = "queued"
        job.error_message = None
        await self.session.flush()

    async def mark_job_running(
        self, document: KnowledgeDocument, job: IngestionJob, *, stage: str
    ) -> None:
        document.status = DocumentStatus.PROCESSING
        document.error_message = None
        job.status = IngestionStatus.RUNNING
        job.stage = stage
        job.attempts += 1
        job.error_message = None
        await self.session.flush()

    async def replace_chunks(
        self,
        *,
        document: KnowledgeDocument,
        knowledge_base: KnowledgeBase,
        drafts: list[ChunkDraft],
        embeddings: list[list[float]],
    ) -> None:
        await self.session.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.tenant_id == document.tenant_id,
                KnowledgeChunk.document_id == document.id,
            )
        )
        chunks = [
            KnowledgeChunk(
                tenant_id=document.tenant_id,
                knowledge_base_id=document.knowledge_base_id,
                document_id=document.id,
                document_version=document.version,
                chunk_index=index,
                content=draft.content,
                heading_path=draft.heading_path,
                source_locator=document.source_url or document.source_filename,
                lexical_text=draft.lexical_text,
                lexical_vector=draft.lexical_text,
                content_hash=draft.content_hash,
                embedding=embeddings[index],
                embedding_model=knowledge_base.embedding_model_name,
                embedding_version=knowledge_base.embedding_version,
                embedding_dimension=knowledge_base.embedding_dimension,
                chunking_version=knowledge_base.chunking_version,
                status=ChunkStatus.ACTIVE,
            )
            for index, draft in enumerate(drafts)
        ]
        self.session.add_all(chunks)
        await self.session.flush()

    async def mark_ingestion_completed(
        self, document: KnowledgeDocument, job: IngestionJob
    ) -> None:
        if document.supersedes_document_id is not None:
            previous = await self.session.get(KnowledgeDocument, document.supersedes_document_id)
            if previous is not None and previous.tenant_id == document.tenant_id:
                previous.status = DocumentStatus.DISABLED
        document.status = DocumentStatus.READY
        document.error_message = None
        job.status = IngestionStatus.COMPLETED
        job.stage = "published"
        job.error_message = None
        await self.session.flush()

    async def mark_ingestion_failed(
        self, document: KnowledgeDocument, job: IngestionJob, *, error: str
    ) -> None:
        document.status = DocumentStatus.FAILED
        document.error_message = error[:2000]
        job.status = IngestionStatus.FAILED
        job.stage = "failed"
        job.error_message = error[:2000]
        await self.session.flush()

    async def delete_document(self, document: KnowledgeDocument) -> None:
        document.status = DocumentStatus.DELETED
        await self.session.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.tenant_id == document.tenant_id,
                KnowledgeChunk.document_id == document.id,
            )
        )
        await self.session.flush()

    async def search(
        self,
        *,
        tenant_id: UUID,
        base_id: UUID,
        query_vector: list[float],
        lexical_query: str,
        limit: int,
        keyword_score_threshold: float = 0.15,
        vector_similarity_threshold: float = 0.72,
    ) -> list[RetrievedChunk]:
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            return await self._search_postgresql(
                tenant_id=tenant_id,
                base_id=base_id,
                query_vector=query_vector,
                lexical_query=lexical_query,
                limit=limit,
                keyword_score_threshold=keyword_score_threshold,
                vector_similarity_threshold=vector_similarity_threshold,
            )
        return await self._search_portable(
            tenant_id=tenant_id,
            base_id=base_id,
            query_vector=query_vector,
            lexical_query=lexical_query,
            limit=limit,
            keyword_score_threshold=keyword_score_threshold,
            vector_similarity_threshold=vector_similarity_threshold,
        )

    async def _search_postgresql(
        self,
        *,
        tenant_id: UUID,
        base_id: UUID,
        query_vector: list[float],
        lexical_query: str,
        limit: int,
        keyword_score_threshold: float,
        vector_similarity_threshold: float,
    ) -> list[RetrievedChunk]:
        filters = (
            KnowledgeChunk.tenant_id == tenant_id,
            KnowledgeChunk.knowledge_base_id == base_id,
            KnowledgeChunk.status == ChunkStatus.ACTIVE,
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.status == DocumentStatus.READY,
        )
        distance = KnowledgeChunk.embedding.cosine_distance(query_vector).label("distance")
        vector_statement = (
            select(KnowledgeChunk, KnowledgeDocument, distance)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(*filters)
            .order_by(distance)
            .limit(20)
        )
        vector_rows = list((await self.session.execute(vector_statement)).tuples())

        lexical_tokens = [
            token for token in lexical_query.split() if any(char.isalnum() for char in token)
        ]
        ts_query = func.websearch_to_tsquery("simple", " OR ".join(lexical_tokens))
        vector_expression = KnowledgeChunk.lexical_vector
        keyword_rank = func.ts_rank_cd(vector_expression, ts_query).label("keyword_rank")
        keyword_statement = (
            select(KnowledgeChunk, KnowledgeDocument, keyword_rank)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(*filters, vector_expression.bool_op("@@")(ts_query))
            .order_by(keyword_rank.desc())
            .limit(20)
        )
        keyword_rows = (
            list((await self.session.execute(keyword_statement)).tuples()) if lexical_tokens else []
        )
        return self._fuse(
            vector_rows,
            keyword_rows,
            limit,
            keyword_score_threshold=keyword_score_threshold,
            vector_similarity_threshold=vector_similarity_threshold,
        )

    async def _search_portable(
        self,
        *,
        tenant_id: UUID,
        base_id: UUID,
        query_vector: list[float],
        lexical_query: str,
        limit: int,
        keyword_score_threshold: float,
        vector_similarity_threshold: float,
    ) -> list[RetrievedChunk]:
        statement = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(
                KnowledgeChunk.tenant_id == tenant_id,
                KnowledgeChunk.knowledge_base_id == base_id,
                KnowledgeChunk.status == ChunkStatus.ACTIVE,
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.status == DocumentStatus.READY,
            )
        )
        rows = list((await self.session.execute(statement)).tuples())
        tokens = set(lexical_query.split())
        vector_rows: list[tuple[KnowledgeChunk, KnowledgeDocument, float]] = []
        keyword_rows: list[tuple[KnowledgeChunk, KnowledgeDocument, float]] = []
        for chunk, document in rows:
            similarity = self._cosine(query_vector, list(chunk.embedding))
            vector_rows.append((chunk, document, 1.0 - similarity))
            chunk_tokens = set(chunk.lexical_text.split())
            overlap = len(tokens & chunk_tokens) / max(len(tokens), 1)
            if overlap > 0:
                keyword_rows.append((chunk, document, overlap))
        vector_rows.sort(key=lambda row: row[2])
        keyword_rows.sort(key=lambda row: row[2], reverse=True)
        return self._fuse(
            vector_rows[:20],
            keyword_rows[:20],
            limit,
            keyword_score_threshold=keyword_score_threshold,
            vector_similarity_threshold=vector_similarity_threshold,
        )

    @staticmethod
    def _fuse(
        vector_rows: list[tuple[KnowledgeChunk, KnowledgeDocument, Any]],
        keyword_rows: list[tuple[KnowledgeChunk, KnowledgeDocument, Any]],
        limit: int,
        *,
        keyword_score_threshold: float = 0.15,
        vector_similarity_threshold: float = 0.72,
    ) -> list[RetrievedChunk]:
        values: dict[UUID, dict[str, Any]] = {}
        for rank, (chunk, document, distance) in enumerate(vector_rows, start=1):
            values[chunk.id] = {
                "chunk": chunk,
                "document": document,
                "score": 1.0 / (60 + rank),
                "vector_similarity": max(0.0, 1.0 - float(distance)),
                "keyword_score": 0.0,
                "keyword_score_threshold": keyword_score_threshold,
                "vector_similarity_threshold": vector_similarity_threshold,
            }
        for rank, (chunk, document, keyword_score) in enumerate(keyword_rows, start=1):
            value = values.setdefault(
                chunk.id,
                {
                    "chunk": chunk,
                    "document": document,
                    "score": 0.0,
                    "vector_similarity": 0.0,
                    "keyword_score": 0.0,
                    "keyword_score_threshold": keyword_score_threshold,
                    "vector_similarity_threshold": vector_similarity_threshold,
                },
            )
            value["score"] += 1.0 / (60 + rank)
            value["keyword_score"] = float(keyword_score)
        ordered = sorted(
            values.values(),
            key=lambda item: (
                item["score"],
                item["keyword_score"],
                item["vector_similarity"],
            ),
            reverse=True,
        )
        return [RetrievedChunk(**value) for value in ordered[:limit]]

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0

    async def add_citations(
        self, *, tenant_id: UUID, message_id: UUID, results: list[RetrievedChunk]
    ) -> list[Citation]:
        citations = [
            Citation(
                tenant_id=tenant_id,
                message_id=message_id,
                document_id=result.document.id,
                chunk_id=result.chunk.id,
                quote=result.chunk.content[:1000],
                source_title=result.document.title,
                source_url=result.document.source_url,
                score=result.score,
            )
            for result in results
        ]
        self.session.add_all(citations)
        await self.session.flush()
        return citations

    async def list_citations(self, *, tenant_id: UUID, message_id: UUID) -> list[Citation]:
        statement = (
            select(Citation)
            .where(Citation.tenant_id == tenant_id, Citation.message_id == message_id)
            .order_by(Citation.score.desc(), Citation.id)
        )
        return list(await self.session.scalars(statement))

    async def list_citations_for_messages(
        self, *, tenant_id: UUID, message_ids: list[UUID]
    ) -> list[Citation]:
        if not message_ids:
            return []
        statement = (
            select(Citation)
            .where(Citation.tenant_id == tenant_id, Citation.message_id.in_(message_ids))
            .order_by(Citation.message_id, Citation.score.desc(), Citation.id)
        )
        return list(await self.session.scalars(statement))

    async def get_citation_document(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        conversation_id: UUID,
        citation_id: UUID,
    ) -> KnowledgeDocument | None:
        statement = (
            select(KnowledgeDocument)
            .join(Citation, Citation.document_id == KnowledgeDocument.id)
            .join(Message, Message.id == Citation.message_id)
            .where(
                Citation.id == citation_id,
                Citation.tenant_id == tenant_id,
                KnowledgeDocument.tenant_id == tenant_id,
                Message.tenant_id == tenant_id,
                Message.application_id == application_id,
                Message.conversation_id == conversation_id,
            )
        )
        return cast(KnowledgeDocument | None, await self.session.scalar(statement))
