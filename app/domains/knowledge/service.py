from __future__ import annotations

import hashlib
import mimetypes
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import StaffPrincipal
from app.domains.applications.models import Application
from app.domains.applications.repository import ApplicationRepository
from app.domains.audit.repository import AuditRepository
from app.domains.knowledge.models import (
    DocumentStatus,
    IngestionJob,
    IngestionStatus,
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeDocument,
)
from app.domains.knowledge.parsing import SUPPORTED_MIME_TYPES, chunk_text, extract_text, lexicalize
from app.domains.knowledge.repository import KnowledgeRepository, RetrievedChunk
from app.domains.knowledge.schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
)
from app.domains.model_gateway.models import ModelPurpose, ModelStatus, ProviderStatus
from app.domains.model_gateway.repository import ModelGatewayRepository
from app.providers.llm.factory import build_embedding_provider
from app.providers.storage.base import ObjectStorage

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024


class KnowledgeBaseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.knowledge = KnowledgeRepository(session)
        self.models = ModelGatewayRepository(session)
        self.applications = ApplicationRepository(session)
        self.audit = AuditRepository(session)

    async def create(
        self,
        *,
        tenant_id: UUID,
        request: KnowledgeBaseCreate,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> KnowledgeBase:
        model_config = await self.models.get_model_config(
            tenant_id=tenant_id,
            model_config_id=request.embedding_model_config_id,
        )
        if (
            model_config is None
            or model_config.purpose != ModelPurpose.EMBEDDING
            or model_config.embedding_dimension is None
        ):
            raise AppError(
                status_code=400,
                code="embedding_model_required",
                title="Embedding model required",
                detail="The knowledge base requires a tenant embedding model configuration.",
            )
        account = await self.models.get_available_account(
            account_id=model_config.provider_account_id, tenant_id=tenant_id
        )
        if account is None or account.status != ProviderStatus.READY:
            raise AppError(
                status_code=400,
                code="provider_account_not_ready",
                title="Provider account not ready",
                detail="The embedding provider account must pass its connection test.",
            )
        try:
            knowledge_base = await self.knowledge.create_base(
                tenant_id=tenant_id,
                name=request.name.strip(),
                description=request.description.strip(),
                model_config=model_config,
                embedding_version=request.embedding_version,
                keyword_score_threshold=request.keyword_score_threshold,
                vector_similarity_threshold=request.vector_similarity_threshold,
            )
            model_config.status = ModelStatus.ACTIVE
            await self._audit(actor, "knowledge_base.create", knowledge_base.id, request_id)
            await self.session.commit()
            await self.session.refresh(knowledge_base)
            return knowledge_base
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                status_code=409,
                code="knowledge_base_name_conflict",
                title="Knowledge base already exists",
                detail="A knowledge base with this name already exists in the tenant.",
            ) from exc

    async def list_bases(self, tenant_id: UUID) -> list[KnowledgeBase]:
        return await self.knowledge.list_bases(tenant_id)

    async def update(
        self,
        *,
        tenant_id: UUID,
        base_id: UUID,
        request: KnowledgeBaseUpdate,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> KnowledgeBase:
        knowledge_base = await self._get_base(tenant_id, base_id)
        if request.name is not None:
            knowledge_base.name = request.name.strip()
        if request.description is not None:
            knowledge_base.description = request.description.strip()
        if request.status is not None:
            knowledge_base.status = request.status
        if request.keyword_score_threshold is not None:
            knowledge_base.keyword_score_threshold = request.keyword_score_threshold
        if request.vector_similarity_threshold is not None:
            knowledge_base.vector_similarity_threshold = request.vector_similarity_threshold
        try:
            await self.session.flush()
            await self._audit(actor, "knowledge_base.update", knowledge_base.id, request_id)
            await self.session.commit()
            await self.session.refresh(knowledge_base)
            return knowledge_base
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                status_code=409,
                code="knowledge_base_name_conflict",
                title="Knowledge base already exists",
                detail="A knowledge base with this name already exists in the tenant.",
            ) from exc

    async def bind(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        base_id: UUID,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> None:
        knowledge_base = await self._get_base(tenant_id, base_id)
        application = await self.applications.get_by_id(
            tenant_id=tenant_id, application_id=application_id
        )
        if application is None:
            raise AppError(
                status_code=404,
                code="application_not_found",
                title="Application not found",
                detail="The requested application does not exist in this tenant.",
            )
        await self.knowledge.bind(
            tenant_id=tenant_id,
            application_id=application.id,
            base_id=knowledge_base.id,
        )
        await self._audit(actor, "knowledge_base.bind", knowledge_base.id, request_id)
        await self.session.commit()

    async def list_bound_applications(self, *, tenant_id: UUID, base_id: UUID) -> list[Application]:
        await self._get_base(tenant_id, base_id)
        return await self.knowledge.list_bound_applications(
            tenant_id=tenant_id,
            base_id=base_id,
        )

    async def unbind(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        base_id: UUID,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> None:
        await self._get_base(tenant_id, base_id)
        await self.knowledge.unbind(
            tenant_id=tenant_id, application_id=application_id, base_id=base_id
        )
        await self._audit(actor, "knowledge_base.unbind", base_id, request_id)
        await self.session.commit()

    async def search(
        self, *, tenant_id: UUID, base_id: UUID, query: str, top_k: int
    ) -> list[RetrievedChunk]:
        knowledge_base = await self._get_base(tenant_id, base_id)
        if knowledge_base.status != KnowledgeBaseStatus.ACTIVE:
            return []
        model_config = await self.models.get_model_config(
            tenant_id=tenant_id,
            model_config_id=knowledge_base.embedding_model_config_id,
        )
        if model_config is None or model_config.embedding_dimension is None:
            raise AppError(
                status_code=503,
                code="embedding_model_unavailable",
                title="Embedding model unavailable",
                detail="The knowledge base embedding model is unavailable.",
            )
        account = await self.models.get_available_account(
            account_id=model_config.provider_account_id, tenant_id=tenant_id
        )
        if account is None or account.status != ProviderStatus.READY:
            raise AppError(
                status_code=503,
                code="embedding_provider_unavailable",
                title="Embedding provider unavailable",
                detail="The knowledge base embedding provider is unavailable.",
            )
        provider = build_embedding_provider(account)
        vectors = await provider.embed(
            texts=[query],
            model=model_config.model_name,
            dimensions=model_config.embedding_dimension,
        )
        if not vectors or len(vectors[0]) != knowledge_base.embedding_dimension:
            raise AppError(
                status_code=502,
                code="embedding_dimension_mismatch",
                title="Embedding dimension mismatch",
                detail="The provider returned an unexpected embedding dimension.",
            )
        return await self.knowledge.search(
            tenant_id=tenant_id,
            base_id=base_id,
            query_vector=vectors[0],
            lexical_query=lexicalize(query),
            limit=top_k,
            keyword_score_threshold=knowledge_base.keyword_score_threshold,
            vector_similarity_threshold=knowledge_base.vector_similarity_threshold,
        )

    async def search_for_application(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        bases = await self.knowledge.list_bound_bases(
            tenant_id=tenant_id, application_id=application_id
        )
        combined: list[RetrievedChunk] = []
        for knowledge_base in bases:
            combined.extend(
                await self.search(
                    tenant_id=tenant_id,
                    base_id=knowledge_base.id,
                    query=query,
                    top_k=max(top_k, 10),
                )
            )
        combined.sort(key=lambda result: result.score, reverse=True)
        return combined[:top_k]

    async def _get_base(self, tenant_id: UUID, base_id: UUID) -> KnowledgeBase:
        knowledge_base = await self.knowledge.get_base(tenant_id=tenant_id, base_id=base_id)
        if knowledge_base is None:
            self._raise_base_not_found()
        return knowledge_base

    async def _audit(
        self, actor: StaffPrincipal, action: str, resource_id: UUID, request_id: str | None
    ) -> None:
        await self.audit.add(
            tenant_id=actor.tenant_id,
            actor_type="staff",
            actor_id=str(actor.user_id),
            action=action,
            resource_type="knowledge_base",
            resource_id=str(resource_id),
            request_id=request_id,
        )

    @staticmethod
    def _raise_base_not_found() -> NoReturn:
        raise AppError(
            status_code=404,
            code="knowledge_base_not_found",
            title="Knowledge base not found",
            detail="The requested knowledge base does not exist in this tenant.",
        )


class DocumentService:
    def __init__(self, session: AsyncSession, storage: ObjectStorage) -> None:
        self.session = session
        self.storage = storage
        self.knowledge = KnowledgeRepository(session)
        self.audit = AuditRepository(session)

    async def upload(
        self,
        *,
        tenant_id: UUID,
        base_id: UUID,
        title: str,
        filename: str,
        mime_type: str | None,
        content: bytes,
        source_url: str | None,
        replace_document_id: UUID | None,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> tuple[KnowledgeDocument, IngestionJob]:
        knowledge_base = await self.knowledge.get_base(tenant_id=tenant_id, base_id=base_id)
        if knowledge_base is None:
            KnowledgeBaseService._raise_base_not_found()
        if not content or len(content) > MAX_DOCUMENT_BYTES:
            raise AppError(
                status_code=413,
                code="document_size_invalid",
                title="Document size invalid",
                detail="Documents must contain data and may not exceed 10 MiB.",
            )
        safe_filename = Path(filename).name[:300]
        resolved_mime = self._resolve_mime(safe_filename, mime_type)
        self._validate_content(content, resolved_mime)
        if source_url is not None:
            parsed = urlsplit(source_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise AppError(
                    status_code=422,
                    code="source_url_invalid",
                    title="Source URL invalid",
                    detail="source_url must be an absolute HTTP or HTTPS URL.",
                )

        if not await self.knowledge.lock_tenant(tenant_id):
            raise AppError(
                status_code=404,
                code="tenant_not_found",
                title="Tenant not found",
                detail="The tenant no longer exists.",
            )
        supersedes = None
        if replace_document_id is not None:
            supersedes = await self.knowledge.get_document(
                tenant_id=tenant_id,
                base_id=base_id,
                document_id=replace_document_id,
            )
            if supersedes is None or supersedes.status == DocumentStatus.DELETED:
                self._raise_document_not_found()

        content_hash = hashlib.sha256(content).hexdigest()
        duplicate = await self.knowledge.find_duplicate_content(
            tenant_id=tenant_id,
            base_id=base_id,
            content_hash=content_hash,
        )
        if duplicate is not None:
            unchanged = supersedes is not None and duplicate.id == supersedes.id
            raise AppError(
                status_code=409,
                code=("document_content_unchanged" if unchanged else "document_content_duplicate"),
                title=("Document content unchanged" if unchanged else "Duplicate document"),
                detail=(
                    "The replacement has the same content as the current document."
                    if unchanged
                    else "The same content already exists in this knowledge base."
                ),
            )

        settings = get_settings()
        document_count, storage_bytes = await self.knowledge.tenant_document_usage(tenant_id)
        if document_count >= settings.knowledge_document_limit_per_tenant:
            raise AppError(
                status_code=409,
                code="knowledge_document_quota_exceeded",
                title="Document quota exceeded",
                detail="Delete unused documents or increase the tenant document quota.",
            )
        if storage_bytes + len(content) > settings.knowledge_storage_limit_bytes_per_tenant:
            raise AppError(
                status_code=413,
                code="knowledge_storage_quota_exceeded",
                title="Knowledge storage quota exceeded",
                detail="Delete unused documents or increase the tenant storage quota.",
            )

        document_id = uuid4()
        version = supersedes.version + 1 if supersedes else 1
        object_key = (
            f"tenants/{tenant_id}/knowledge/{base_id}/documents/"
            f"{document_id}/v{version}/{safe_filename}"
        )
        await self.storage.put(object_key, content, resolved_mime)
        try:
            document, job = await self.knowledge.create_document(
                document_id=document_id,
                tenant_id=tenant_id,
                base_id=base_id,
                supersedes=supersedes,
                title=title.strip(),
                filename=safe_filename,
                source_url=source_url,
                mime_type=resolved_mime,
                byte_size=len(content),
                object_key=object_key,
                content_hash=content_hash,
            )
            await self.audit.add(
                tenant_id=tenant_id,
                actor_type="staff",
                actor_id=str(actor.user_id),
                action="knowledge_document.upload",
                resource_type="knowledge_document",
                resource_id=str(document.id),
                request_id=request_id,
            )
            await self.session.commit()
            await self.session.refresh(document)
            await self.session.refresh(job)
            return document, job
        except Exception:
            await self.session.rollback()
            await self.storage.delete(object_key)
            raise

    async def list(self, *, tenant_id: UUID, base_id: UUID) -> list[KnowledgeDocument]:
        await self._require_base(tenant_id, base_id)
        return await self.knowledge.list_documents(tenant_id=tenant_id, base_id=base_id)

    async def restore_metadata(
        self,
        *,
        tenant_id: UUID,
        base_id: UUID,
        documents: Sequence[KnowledgeDocument],
    ) -> dict[UUID, tuple[bool, str | None]]:
        knowledge_base = await self._require_base(tenant_id, base_id)
        version_documents = await self.knowledge.list_version_documents(
            tenant_id=tenant_id,
            base_id=base_id,
        )
        metadata: dict[UUID, tuple[bool, str | None]] = {}
        for document in documents:
            if document.status != DocumentStatus.DISABLED:
                metadata[document.id] = (False, None)
            elif knowledge_base.status != KnowledgeBaseStatus.ACTIVE:
                metadata[document.id] = (False, "document_restore_base_disabled")
            elif self._has_ready_version_conflict(document, version_documents):
                metadata[document.id] = (False, "document_restore_version_conflict")
            else:
                metadata[document.id] = (True, None)
        return metadata

    async def get(
        self, *, tenant_id: UUID, base_id: UUID, document_id: UUID
    ) -> tuple[KnowledgeDocument, IngestionJob]:
        document = await self.knowledge.get_document(
            tenant_id=tenant_id, base_id=base_id, document_id=document_id
        )
        if document is None or document.status == DocumentStatus.DELETED:
            self._raise_document_not_found()
        job = await self.knowledge.get_job(tenant_id=tenant_id, document_id=document_id)
        if job is None:
            raise AppError(
                status_code=500,
                code="ingestion_job_missing",
                title="Ingestion job missing",
                detail="The document ingestion state is inconsistent.",
            )
        return document, job

    async def update_lifecycle_status(
        self,
        *,
        tenant_id: UUID,
        base_id: UUID,
        document_id: UUID,
        target_status: DocumentStatus,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> KnowledgeDocument:
        knowledge_base = await self.knowledge.get_base_for_update(
            tenant_id=tenant_id,
            base_id=base_id,
        )
        if knowledge_base is None:
            KnowledgeBaseService._raise_base_not_found()
        document = await self.knowledge.get_document_for_update(
            tenant_id=tenant_id,
            base_id=base_id,
            document_id=document_id,
        )
        if document is None or document.status == DocumentStatus.DELETED:
            self._raise_document_not_found()

        previous_status = document.status
        if target_status == DocumentStatus.DISABLED:
            if previous_status != DocumentStatus.READY:
                self._raise_invalid_transition(previous_status, target_status)
        elif target_status == DocumentStatus.READY:
            if previous_status != DocumentStatus.DISABLED:
                self._raise_invalid_transition(previous_status, target_status)
            await self._validate_restore(
                knowledge_base=knowledge_base,
                document=document,
            )
        else:
            self._raise_invalid_transition(previous_status, target_status)

        try:
            await self.knowledge.set_document_retrieval_status(
                document,
                status=target_status,
            )
            action = (
                "knowledge_document.disable"
                if target_status == DocumentStatus.DISABLED
                else "knowledge_document.restore"
            )
            await self.audit.add(
                tenant_id=tenant_id,
                actor_type="staff",
                actor_id=str(actor.user_id),
                action=action,
                resource_type="knowledge_document",
                resource_id=str(document.id),
                request_id=request_id,
                details={
                    "from_status": previous_status.value,
                    "to_status": target_status.value,
                },
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(document)
        return document

    async def delete(
        self,
        *,
        tenant_id: UUID,
        base_id: UUID,
        document_id: UUID,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> None:
        knowledge_base = await self.knowledge.get_base_for_update(
            tenant_id=tenant_id,
            base_id=base_id,
        )
        if knowledge_base is None:
            KnowledgeBaseService._raise_base_not_found()
        document = await self.knowledge.get_document_for_update(
            tenant_id=tenant_id,
            base_id=base_id,
            document_id=document_id,
        )
        if document is None:
            self._raise_document_not_found()
        if document.status == DocumentStatus.DELETED:
            cleanup_pending = document.object_cleanup_pending
            await self.session.rollback()
            if cleanup_pending:
                await self._cleanup_stored_object(document.id, raise_on_failure=True)
            return
        if document.status in {DocumentStatus.UPLOADED, DocumentStatus.PROCESSING}:
            raise AppError(
                status_code=409,
                code="document_ingestion_in_progress",
                title="Document ingestion in progress",
                detail="Wait for ingestion to finish before deleting this document.",
            )
        try:
            await self.knowledge.mark_document_deleted(document)
            await self.audit.add(
                tenant_id=tenant_id,
                actor_type="staff",
                actor_id=str(actor.user_id),
                action="knowledge_document.delete",
                resource_type="knowledge_document",
                resource_id=str(document.id),
                request_id=request_id,
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self._cleanup_stored_object(document.id, raise_on_failure=True)

    async def cleanup_pending_objects(self, *, limit: int = 100) -> dict[str, int]:
        document_ids = await self.knowledge.list_pending_object_cleanup_ids(limit=limit)
        await self.session.rollback()
        completed = 0
        failed = 0
        for document_id in document_ids:
            if await self._cleanup_stored_object(document_id, raise_on_failure=False):
                completed += 1
            else:
                failed += 1
        return {
            "selected": len(document_ids),
            "completed": completed,
            "failed": failed,
        }

    async def retry(
        self,
        *,
        tenant_id: UUID,
        base_id: UUID,
        document_id: UUID,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> tuple[KnowledgeDocument, IngestionJob]:
        document = await self.knowledge.get_document_for_update(
            tenant_id=tenant_id,
            base_id=base_id,
            document_id=document_id,
        )
        if document is None or document.status == DocumentStatus.DELETED:
            self._raise_document_not_found()
        job = await self.knowledge.get_job(tenant_id=tenant_id, document_id=document_id)
        if job is None:
            raise AppError(
                status_code=500,
                code="ingestion_job_missing",
                title="Ingestion job missing",
                detail="The document ingestion state is inconsistent.",
            )
        if document.status not in {DocumentStatus.UPLOADED, DocumentStatus.FAILED}:
            raise AppError(
                status_code=409,
                code="document_not_retryable",
                title="Document cannot be retried",
                detail="Only queued or failed documents can be queued for ingestion.",
            )
        await self.knowledge.prepare_retry(document, job)
        await self.audit.add(
            tenant_id=tenant_id,
            actor_type="staff",
            actor_id=str(actor.user_id),
            action="knowledge_document.retry",
            resource_type="knowledge_document",
            resource_id=str(document.id),
            request_id=request_id,
        )
        await self.session.commit()
        await self.session.refresh(document)
        await self.session.refresh(job)
        return document, job

    async def _require_base(self, tenant_id: UUID, base_id: UUID) -> KnowledgeBase:
        knowledge_base = await self.knowledge.get_base(tenant_id=tenant_id, base_id=base_id)
        if knowledge_base is None:
            KnowledgeBaseService._raise_base_not_found()
        return knowledge_base

    async def _validate_restore(
        self,
        *,
        knowledge_base: KnowledgeBase,
        document: KnowledgeDocument,
    ) -> None:
        if knowledge_base.status != KnowledgeBaseStatus.ACTIVE:
            raise AppError(
                status_code=409,
                code="document_restore_base_disabled",
                title="Document cannot be restored",
                detail="Enable the knowledge base before restoring this document.",
            )

        job = await self.knowledge.get_job(
            tenant_id=document.tenant_id,
            document_id=document.id,
        )
        if job is None or job.status != IngestionStatus.COMPLETED or job.stage != "published":
            self._raise_restore_index_invalid()

        try:
            content = await self.storage.get(document.object_key)
        except AppError as exc:
            raise AppError(
                status_code=409,
                code="document_restore_source_invalid",
                title="Document source is unavailable",
                detail="The original object is unavailable; upload a replacement document.",
            ) from exc
        if len(content) != document.byte_size or hashlib.sha256(content).hexdigest() != (
            document.content_hash
        ):
            raise AppError(
                status_code=409,
                code="document_restore_source_invalid",
                title="Document source is invalid",
                detail="The original object no longer matches this document version.",
            )

        chunks = await self.knowledge.list_document_chunks(
            tenant_id=document.tenant_id,
            base_id=document.knowledge_base_id,
            document_id=document.id,
        )
        expected_indexes = list(range(len(chunks)))
        if not chunks or [chunk.chunk_index for chunk in chunks] != expected_indexes:
            self._raise_restore_index_invalid()
        if any(
            chunk.document_version != document.version
            or chunk.embedding_model != knowledge_base.embedding_model_name
            or chunk.embedding_version != knowledge_base.embedding_version
            or chunk.embedding_dimension != knowledge_base.embedding_dimension
            or len(chunk.embedding) != knowledge_base.embedding_dimension
            or chunk.chunking_version != knowledge_base.chunking_version
            for chunk in chunks
        ):
            self._raise_restore_index_invalid()

        version_documents = await self.knowledge.list_version_documents(
            tenant_id=document.tenant_id,
            base_id=document.knowledge_base_id,
        )
        if self._has_ready_version_conflict(document, version_documents):
            raise AppError(
                status_code=409,
                code="document_restore_version_conflict",
                title="Document version cannot be restored",
                detail="Another published version in this document chain is currently active.",
            )

    async def _cleanup_stored_object(self, document_id: UUID, *, raise_on_failure: bool) -> bool:
        document = await self.knowledge.get_pending_object_cleanup_for_update(document_id)
        if document is None:
            await self.session.rollback()
            return True
        try:
            await self.storage.delete(document.object_key)
        except Exception as exc:
            await self.knowledge.mark_object_cleanup_failed(document, error=str(exc))
            await self.session.commit()
            if raise_on_failure:
                raise AppError(
                    status_code=503,
                    code="object_storage_delete_failed",
                    title="Object storage unavailable",
                    detail=(
                        "The document is deleted and hidden. Stored file cleanup will retry "
                        "automatically."
                    ),
                ) from exc
            return False
        await self.knowledge.mark_object_cleanup_completed(document)
        await self.session.commit()
        return True

    @staticmethod
    def _has_ready_version_conflict(
        document: KnowledgeDocument,
        candidates: Sequence[KnowledgeDocument],
    ) -> bool:
        by_id = {candidate.id: candidate for candidate in candidates}
        connected: dict[UUID, set[UUID]] = {candidate.id: set() for candidate in candidates}
        for candidate in candidates:
            parent_id = candidate.supersedes_document_id
            if parent_id is not None and parent_id in connected:
                connected[candidate.id].add(parent_id)
                connected[parent_id].add(candidate.id)

        pending = [document.id]
        visited: set[UUID] = set()
        while pending:
            candidate_id = pending.pop()
            if candidate_id in visited:
                continue
            visited.add(candidate_id)
            current = by_id.get(candidate_id)
            if (
                current is not None
                and current.id != document.id
                and current.status == DocumentStatus.READY
            ):
                return True
            pending.extend(connected.get(candidate_id, ()))
        return False

    @staticmethod
    def _raise_invalid_transition(
        current_status: DocumentStatus,
        target_status: DocumentStatus,
    ) -> NoReturn:
        raise AppError(
            status_code=409,
            code="document_status_transition_invalid",
            title="Document status transition is invalid",
            detail=(
                f"A document cannot transition from {current_status.value} "
                f"to {target_status.value}."
            ),
        )

    @staticmethod
    def _raise_restore_index_invalid() -> NoReturn:
        raise AppError(
            status_code=409,
            code="document_restore_index_invalid",
            title="Document index is unavailable",
            detail=(
                "The published index is incomplete or incompatible; upload a replacement document."
            ),
        )

    @staticmethod
    def _resolve_mime(filename: str, provided: str | None) -> str:
        guessed, _ = mimetypes.guess_type(filename)
        mime_type = provided if provided in SUPPORTED_MIME_TYPES else guessed
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise AppError(
                status_code=415,
                code="document_type_unsupported",
                title="Unsupported document type",
                detail="Only UTF-8 TXT, Markdown, and text-based PDF files are supported.",
            )
        return mime_type

    @staticmethod
    def _validate_content(content: bytes, mime_type: str) -> None:
        if mime_type == "application/pdf":
            if not content.startswith(b"%PDF-"):
                raise AppError(
                    status_code=422,
                    code="document_content_invalid",
                    title="Document content invalid",
                    detail="The uploaded file does not contain a valid PDF signature.",
                )
            return
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AppError(
                status_code=422,
                code="document_encoding_invalid",
                title="Document encoding invalid",
                detail="Text and Markdown documents must use UTF-8 encoding.",
            ) from exc
        if "\x00" in text:
            raise AppError(
                status_code=422,
                code="document_content_invalid",
                title="Document content invalid",
                detail="Text documents may not contain null bytes.",
            )

    @staticmethod
    def _raise_document_not_found() -> NoReturn:
        raise AppError(
            status_code=404,
            code="document_not_found",
            title="Document not found",
            detail="The requested document does not exist in this knowledge base.",
        )


class IngestionService:
    def __init__(self, session: AsyncSession, storage: ObjectStorage) -> None:
        self.session = session
        self.storage = storage
        self.knowledge = KnowledgeRepository(session)

    async def process(self, *, tenant_id: UUID, document_id: UUID) -> None:
        context = await self.knowledge.get_ingestion_context(
            tenant_id=tenant_id, document_id=document_id
        )
        if context is None:
            raise AppError(
                status_code=404,
                code="ingestion_context_not_found",
                title="Ingestion context not found",
                detail="The document or its embedding configuration is unavailable.",
            )
        document, knowledge_base, job, model_config, account = context
        if document.status == DocumentStatus.READY and job.stage == "published":
            return
        try:
            await self.knowledge.mark_job_running(document, job, stage="reading")
            await self.session.commit()
            content = await self.storage.get(document.object_key)
            text = extract_text(content, document.mime_type)
            drafts = chunk_text(text)
            job.stage = "embedding"
            await self.session.commit()
            provider = build_embedding_provider(account)
            embeddings = await provider.embed(
                texts=[f"{document.title}\n{draft.content}" for draft in drafts],
                model=model_config.model_name,
                dimensions=knowledge_base.embedding_dimension,
            )
            if len(embeddings) != len(drafts) or any(
                len(vector) != knowledge_base.embedding_dimension for vector in embeddings
            ):
                raise AppError(
                    status_code=502,
                    code="embedding_dimension_mismatch",
                    title="Embedding dimension mismatch",
                    detail="The provider returned an unexpected embedding shape.",
                )
            job.stage = "publishing"
            await self.knowledge.replace_chunks(
                document=document,
                knowledge_base=knowledge_base,
                drafts=drafts,
                embeddings=embeddings,
            )
            await self.knowledge.mark_ingestion_completed(document, job)
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            context = await self.knowledge.get_ingestion_context(
                tenant_id=tenant_id, document_id=document_id
            )
            if context is not None:
                failed_document, _, failed_job, _, _ = context
                detail = exc.detail if isinstance(exc, AppError) else str(exc)
                await self.knowledge.mark_ingestion_failed(
                    failed_document, failed_job, error=detail
                )
                await self.session.commit()
            raise
