from typing import Annotated
from uuid import UUID

from celery.exceptions import CeleryError
from fastapi import APIRouter, File, Form, Request, UploadFile, status

from app.api.dependencies import SessionDependency, StorageDependency, TenantAdminDependency
from app.core.errors import AppError
from app.domains.applications.schemas import ApplicationResponse
from app.domains.knowledge.schemas import (
    DocumentAcceptedResponse,
    DocumentResponse,
    IngestionJobResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    KnowledgeSearchRequest,
    SearchResultResponse,
)
from app.domains.knowledge.service import (
    MAX_DOCUMENT_BYTES,
    DocumentService,
    KnowledgeBaseService,
)
from app.workers.knowledge import ingest_knowledge_document

router = APIRouter(prefix="/admin/knowledge-bases", tags=["knowledge-bases"])


@router.post(
    "",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createKnowledgeBase",
)
async def create_knowledge_base(
    body: KnowledgeBaseCreate,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> KnowledgeBaseResponse:
    assert actor.tenant_id is not None
    knowledge_base = await KnowledgeBaseService(session).create(
        tenant_id=actor.tenant_id,
        request=body,
        actor=actor,
        request_id=request.state.request_id,
    )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.get(
    "",
    response_model=list[KnowledgeBaseResponse],
    operation_id="listKnowledgeBases",
)
async def list_knowledge_bases(
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> list[KnowledgeBaseResponse]:
    assert actor.tenant_id is not None
    items = await KnowledgeBaseService(session).list_bases(actor.tenant_id)
    return [KnowledgeBaseResponse.model_validate(item) for item in items]


@router.patch(
    "/{base_id}",
    response_model=KnowledgeBaseResponse,
    operation_id="updateKnowledgeBase",
)
async def update_knowledge_base(
    base_id: UUID,
    body: KnowledgeBaseUpdate,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> KnowledgeBaseResponse:
    assert actor.tenant_id is not None
    item = await KnowledgeBaseService(session).update(
        tenant_id=actor.tenant_id,
        base_id=base_id,
        request=body,
        actor=actor,
        request_id=request.state.request_id,
    )
    return KnowledgeBaseResponse.model_validate(item)


@router.put(
    "/{base_id}/applications/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="bindKnowledgeBase",
)
async def bind_knowledge_base(
    base_id: UUID,
    application_id: UUID,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> None:
    assert actor.tenant_id is not None
    await KnowledgeBaseService(session).bind(
        tenant_id=actor.tenant_id,
        application_id=application_id,
        base_id=base_id,
        actor=actor,
        request_id=request.state.request_id,
    )


@router.get(
    "/{base_id}/applications",
    response_model=list[ApplicationResponse],
    operation_id="listKnowledgeBaseApplications",
)
async def list_knowledge_base_applications(
    base_id: UUID,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> list[ApplicationResponse]:
    assert actor.tenant_id is not None
    applications = await KnowledgeBaseService(session).list_bound_applications(
        tenant_id=actor.tenant_id,
        base_id=base_id,
    )
    return [ApplicationResponse.model_validate(application) for application in applications]


@router.delete(
    "/{base_id}/applications/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="unbindKnowledgeBase",
)
async def unbind_knowledge_base(
    base_id: UUID,
    application_id: UUID,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> None:
    assert actor.tenant_id is not None
    await KnowledgeBaseService(session).unbind(
        tenant_id=actor.tenant_id,
        application_id=application_id,
        base_id=base_id,
        actor=actor,
        request_id=request.state.request_id,
    )


@router.post(
    "/{base_id}/documents",
    response_model=DocumentAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="uploadKnowledgeDocument",
)
async def upload_document(
    base_id: UUID,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
    storage: StorageDependency,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=300)],
    source_url: Annotated[str | None, Form(max_length=1000)] = None,
    replace_document_id: Annotated[UUID | None, Form()] = None,
) -> DocumentAcceptedResponse:
    assert actor.tenant_id is not None
    filename = file.filename or ""
    if not filename:
        raise AppError(
            status_code=422,
            code="document_filename_required",
            title="Document filename required",
            detail="The uploaded document must include a filename.",
        )
    content = await file.read(MAX_DOCUMENT_BYTES + 1)
    document, job = await DocumentService(session, storage).upload(
        tenant_id=actor.tenant_id,
        base_id=base_id,
        title=title,
        filename=filename,
        mime_type=file.content_type,
        content=content,
        source_url=source_url,
        replace_document_id=replace_document_id,
        actor=actor,
        request_id=request.state.request_id,
    )
    _enqueue_ingestion(actor.tenant_id, document.id)
    return DocumentAcceptedResponse(
        document=DocumentResponse.model_validate(document),
        job=IngestionJobResponse.model_validate(job),
    )


@router.get(
    "/{base_id}/documents",
    response_model=list[DocumentResponse],
    operation_id="listKnowledgeDocuments",
)
async def list_documents(
    base_id: UUID,
    actor: TenantAdminDependency,
    session: SessionDependency,
    storage: StorageDependency,
) -> list[DocumentResponse]:
    assert actor.tenant_id is not None
    items = await DocumentService(session, storage).list(tenant_id=actor.tenant_id, base_id=base_id)
    return [DocumentResponse.model_validate(item) for item in items]


@router.get(
    "/{base_id}/documents/{document_id}",
    response_model=DocumentAcceptedResponse,
    operation_id="getKnowledgeDocument",
)
async def get_document(
    base_id: UUID,
    document_id: UUID,
    actor: TenantAdminDependency,
    session: SessionDependency,
    storage: StorageDependency,
) -> DocumentAcceptedResponse:
    assert actor.tenant_id is not None
    document, job = await DocumentService(session, storage).get(
        tenant_id=actor.tenant_id,
        base_id=base_id,
        document_id=document_id,
    )
    return DocumentAcceptedResponse(
        document=DocumentResponse.model_validate(document),
        job=IngestionJobResponse.model_validate(job),
    )


@router.post(
    "/{base_id}/documents/{document_id}/retry",
    response_model=DocumentAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="retryKnowledgeDocumentIngestion",
)
async def retry_document(
    base_id: UUID,
    document_id: UUID,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
    storage: StorageDependency,
) -> DocumentAcceptedResponse:
    assert actor.tenant_id is not None
    document, job = await DocumentService(session, storage).retry(
        tenant_id=actor.tenant_id,
        base_id=base_id,
        document_id=document_id,
        actor=actor,
        request_id=request.state.request_id,
    )
    _enqueue_ingestion(actor.tenant_id, document.id)
    return DocumentAcceptedResponse(
        document=DocumentResponse.model_validate(document),
        job=IngestionJobResponse.model_validate(job),
    )


@router.delete(
    "/{base_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteKnowledgeDocument",
)
async def delete_document(
    base_id: UUID,
    document_id: UUID,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
    storage: StorageDependency,
) -> None:
    assert actor.tenant_id is not None
    await DocumentService(session, storage).delete(
        tenant_id=actor.tenant_id,
        base_id=base_id,
        document_id=document_id,
        actor=actor,
        request_id=request.state.request_id,
    )


@router.post(
    "/{base_id}/search",
    response_model=list[SearchResultResponse],
    operation_id="searchKnowledgeBase",
)
async def search_knowledge_base(
    base_id: UUID,
    body: KnowledgeSearchRequest,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> list[SearchResultResponse]:
    assert actor.tenant_id is not None
    results = await KnowledgeBaseService(session).search(
        tenant_id=actor.tenant_id,
        base_id=base_id,
        query=body.query,
        top_k=body.top_k,
    )
    return [
        SearchResultResponse(
            chunk_id=result.chunk.id,
            document_id=result.document.id,
            document_title=result.document.title,
            source_url=result.document.source_url,
            content=result.chunk.content,
            heading_path=result.chunk.heading_path,
            score=result.score,
            vector_similarity=result.vector_similarity,
            keyword_score=result.keyword_score,
        )
        for result in results
    ]


def _enqueue_ingestion(tenant_id: UUID, document_id: UUID) -> None:
    try:
        ingest_knowledge_document.delay(str(tenant_id), str(document_id))
    except (CeleryError, OSError) as exc:
        raise AppError(
            status_code=503,
            code="ingestion_queue_unavailable",
            title="Ingestion queue unavailable",
            detail=(
                "The document was stored but could not be queued. "
                "Retry ingestion when the worker broker is available."
            ),
        ) from exc
