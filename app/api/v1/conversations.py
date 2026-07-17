from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Header, Query, status
from fastapi.responses import Response, StreamingResponse

from app.api.dependencies import (
    AgentDependency,
    CurrentCustomerDependency,
    SessionDependency,
    StorageDependency,
)
from app.domains.conversations.models import ConversationMode, ConversationStatus
from app.domains.conversations.schemas import (
    AdminConversationPage,
    AdminConversationResponse,
    AdminMessagePage,
    ConversationCreate,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
)
from app.domains.conversations.service import AdminConversationService, ConversationService

router = APIRouter(prefix="/chat/sessions", tags=["customer-chat"])
admin_router = APIRouter(prefix="/admin/conversations", tags=["admin-conversations"])


@admin_router.get("", response_model=AdminConversationPage, operation_id="listAdminConversations")
async def list_admin_conversations(
    actor: AgentDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[
        UUID | None,
        Query(description="Return conversations older than this ID"),
    ] = None,
    application_id: UUID | None = None,
    conversation_status: Annotated[ConversationStatus | None, Query(alias="status")] = None,
    mode: ConversationMode | None = None,
) -> AdminConversationPage:
    return await AdminConversationService(session).list_conversations(
        actor=actor,
        limit=limit,
        before_id=before,
        application_id=application_id,
        status=conversation_status,
        mode=mode,
    )


@admin_router.get(
    "/{conversation_id}",
    response_model=AdminConversationResponse,
    operation_id="getAdminConversation",
)
async def get_admin_conversation(
    conversation_id: UUID,
    actor: AgentDependency,
    session: SessionDependency,
) -> AdminConversationResponse:
    return await AdminConversationService(session).get(
        actor=actor,
        conversation_id=conversation_id,
    )


@admin_router.get(
    "/{conversation_id}/messages",
    response_model=AdminMessagePage,
    operation_id="listAdminConversationMessages",
)
async def list_admin_conversation_messages(
    conversation_id: UUID,
    actor: AgentDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    before: Annotated[UUID | None, Query(description="Return messages older than this ID")] = None,
) -> AdminMessagePage:
    return await AdminConversationService(session).list_messages(
        actor=actor,
        conversation_id=conversation_id,
        limit=limit,
        before_id=before,
    )


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createChatSession",
)
async def create_session(
    _: ConversationCreate,
    principal: CurrentCustomerDependency,
    session: SessionDependency,
) -> ConversationResponse:
    conversation = await ConversationService(session).create_session(principal)
    return ConversationResponse.model_validate(conversation)


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    operation_id="getChatSession",
)
async def get_session(
    conversation_id: UUID,
    principal: CurrentCustomerDependency,
    session: SessionDependency,
) -> ConversationResponse:
    conversation = await ConversationService(session).get_session(principal, conversation_id)
    return ConversationResponse.model_validate(conversation)


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageResponse],
    operation_id="listChatMessages",
)
async def list_messages(
    conversation_id: UUID,
    principal: CurrentCustomerDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    before: Annotated[UUID | None, Query(description="Return messages older than this ID")] = None,
) -> list[MessageResponse]:
    messages = await ConversationService(session).list_messages(
        principal,
        conversation_id,
        limit=limit,
        before_id=before,
    )
    return messages


@router.get(
    "/{conversation_id}/citations/{citation_id}/source",
    response_class=Response,
    responses={
        200: {
            "content": {
                "text/plain": {},
                "text/markdown": {},
                "application/pdf": {},
            },
            "description": "Original uploaded document referenced by this conversation citation.",
        }
    },
    operation_id="getChatCitationSource",
)
async def get_citation_source(
    conversation_id: UUID,
    citation_id: UUID,
    principal: CurrentCustomerDependency,
    session: SessionDependency,
    storage: StorageDependency,
) -> Response:
    document = await ConversationService(session).get_citation_document(
        principal=principal,
        conversation_id=conversation_id,
        citation_id=citation_id,
    )
    content = await storage.get(document.object_key)
    encoded_filename = quote(document.source_filename, safe="")
    return Response(
        content=content,
        media_type=document.mime_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}",
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/{conversation_id}/messages",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": (
                "SSE events: message.started, message.delta, message.completed, message.error"
            ),
        }
    },
    operation_id="streamChatMessage",
)
async def stream_message(
    conversation_id: UUID,
    body: MessageCreate,
    principal: CurrentCustomerDependency,
    session: SessionDependency,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> StreamingResponse:
    service = ConversationService(session)
    prepared = await service.prepare_chat(
        principal=principal,
        conversation_id=conversation_id,
        content=body.content,
        locale=body.locale,
        idempotency_key=idempotency_key,
    )
    return StreamingResponse(
        service.stream_chat(prepared),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
