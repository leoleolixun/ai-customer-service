from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status

from app.api.dependencies import AgentDependency, CurrentCustomerDependency, SessionDependency
from app.domains.conversations.schemas import MessageResponse
from app.domains.handoffs.models import HandoffStatus
from app.domains.handoffs.schemas import (
    HandoffClose,
    HandoffCreate,
    HandoffResponse,
    HumanMessageCreate,
)
from app.domains.handoffs.service import AgentHandoffService, CustomerHandoffService

customer_router = APIRouter(prefix="/chat/sessions", tags=["customer-handoff"])
admin_router = APIRouter(prefix="/admin/handoffs", tags=["agent-handoffs"])


@customer_router.post(
    "/{conversation_id}/handoff",
    response_model=HandoffResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="requestHumanHandoff",
)
async def request_handoff(
    conversation_id: UUID,
    body: HandoffCreate,
    request: Request,
    principal: CurrentCustomerDependency,
    session: SessionDependency,
) -> HandoffResponse:
    handoff = await CustomerHandoffService(session).request(
        principal=principal,
        conversation_id=conversation_id,
        reason=body.reason,
        request_id=request.state.request_id,
    )
    return HandoffResponse.model_validate(handoff)


@customer_router.get(
    "/{conversation_id}/handoff",
    response_model=HandoffResponse,
    operation_id="getHumanHandoff",
)
async def get_handoff(
    conversation_id: UUID,
    principal: CurrentCustomerDependency,
    session: SessionDependency,
) -> HandoffResponse:
    handoff = await CustomerHandoffService(session).get_current(
        principal=principal, conversation_id=conversation_id
    )
    return HandoffResponse.model_validate(handoff)


@customer_router.post(
    "/{conversation_id}/human-messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createCustomerHumanMessage",
)
async def create_customer_human_message(
    conversation_id: UUID,
    body: HumanMessageCreate,
    principal: CurrentCustomerDependency,
    session: SessionDependency,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> MessageResponse:
    return await CustomerHandoffService(session).add_message(
        principal=principal,
        conversation_id=conversation_id,
        content=body.content,
        idempotency_key=idempotency_key,
    )


@admin_router.get(
    "",
    response_model=list[HandoffResponse],
    operation_id="listHumanHandoffs",
)
async def list_handoffs(
    actor: AgentDependency,
    session: SessionDependency,
    handoff_status: Annotated[HandoffStatus | None, Query(alias="status")] = None,
) -> list[HandoffResponse]:
    items = await AgentHandoffService(session).list_handoffs(actor=actor, status=handoff_status)
    return [HandoffResponse.model_validate(item) for item in items]


@admin_router.post(
    "/{handoff_id}/accept",
    response_model=HandoffResponse,
    operation_id="acceptHumanHandoff",
)
async def accept_handoff(
    handoff_id: UUID,
    request: Request,
    actor: AgentDependency,
    session: SessionDependency,
) -> HandoffResponse:
    handoff = await AgentHandoffService(session).accept(
        actor=actor,
        handoff_id=handoff_id,
        request_id=request.state.request_id,
    )
    return HandoffResponse.model_validate(handoff)


@admin_router.get(
    "/{handoff_id}/messages",
    response_model=list[MessageResponse],
    operation_id="listHandoffMessages",
)
async def list_handoff_messages(
    handoff_id: UUID,
    actor: AgentDependency,
    session: SessionDependency,
) -> list[MessageResponse]:
    return await AgentHandoffService(session).list_messages(actor=actor, handoff_id=handoff_id)


@admin_router.post(
    "/{handoff_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAgentMessage",
)
async def create_agent_message(
    handoff_id: UUID,
    body: HumanMessageCreate,
    request: Request,
    actor: AgentDependency,
    session: SessionDependency,
) -> MessageResponse:
    return await AgentHandoffService(session).add_message(
        actor=actor,
        handoff_id=handoff_id,
        content=body.content,
        request_id=request.state.request_id,
    )


@admin_router.post(
    "/{handoff_id}/close",
    response_model=HandoffResponse,
    operation_id="closeHumanHandoff",
)
async def close_handoff(
    handoff_id: UUID,
    body: HandoffClose,
    request: Request,
    actor: AgentDependency,
    session: SessionDependency,
) -> HandoffResponse:
    handoff = await AgentHandoffService(session).close(
        actor=actor,
        handoff_id=handoff_id,
        reason=body.reason,
        request_id=request.state.request_id,
    )
    return HandoffResponse.model_validate(handoff)
