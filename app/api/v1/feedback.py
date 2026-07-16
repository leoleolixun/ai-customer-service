from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.api.dependencies import CurrentCustomerDependency, SessionDependency, TenantAdminDependency
from app.domains.conversations.schemas import (
    AdminFeedbackResponse,
    FeedbackCreate,
    FeedbackResponse,
)
from app.domains.conversations.service import FeedbackService

router = APIRouter(tags=["feedback"])


@router.post(
    "/chat/sessions/{conversation_id}/feedback",
    response_model=FeedbackResponse,
    operation_id="submitConversationFeedback",
)
async def submit_feedback(
    conversation_id: UUID,
    body: FeedbackCreate,
    request: Request,
    principal: CurrentCustomerDependency,
    session: SessionDependency,
) -> FeedbackResponse:
    return await FeedbackService(session).submit(
        principal=principal,
        conversation_id=conversation_id,
        request=body,
        request_id=request.state.request_id,
    )


@router.get(
    "/admin/feedback",
    response_model=list[AdminFeedbackResponse],
    operation_id="listConversationFeedback",
)
async def list_feedback(
    actor: TenantAdminDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AdminFeedbackResponse]:
    assert actor.tenant_id is not None
    return await FeedbackService(session).list_for_admin(
        tenant_id=actor.tenant_id,
        limit=limit,
    )
