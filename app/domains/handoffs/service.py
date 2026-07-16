from typing import NoReturn
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import CustomerPrincipal, StaffPrincipal
from app.domains.audit.repository import AuditRepository
from app.domains.conversations.models import (
    Conversation,
    ConversationMode,
    ConversationStatus,
    Message,
    MessageSender,
)
from app.domains.conversations.repository import ConversationRepository
from app.domains.conversations.schemas import MessageResponse
from app.domains.handoffs.models import HandoffRequest, HandoffStatus
from app.domains.handoffs.repository import HandoffRepository


class CustomerHandoffService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.handoffs = HandoffRepository(session)
        self.conversations = ConversationRepository(session)
        self.audit = AuditRepository(session)

    async def request(
        self,
        *,
        principal: CustomerPrincipal,
        conversation_id: UUID,
        reason: str,
        request_id: str | None,
    ) -> HandoffRequest:
        self._require_scope(principal, "handoff:create")
        conversation = await self._owned_conversation(principal, conversation_id)
        if conversation.status != ConversationStatus.OPEN:
            self._raise_closed()
        existing = await self.handoffs.get_active(
            tenant_id=principal.tenant_id, conversation_id=conversation.id
        )
        if existing is not None:
            return existing
        recent_messages = await self.conversations.get_recent_completed_messages(
            tenant_id=principal.tenant_id,
            conversation_id=conversation.id,
            limit=6,
        )
        summary = self._summary(recent_messages)
        conversation.mode = ConversationMode.HUMAN
        try:
            handoff = await self.handoffs.create(
                conversation=conversation,
                reason=reason.strip(),
                summary=summary,
            )
            await self._audit_customer(principal, "handoff.request", handoff, request_id)
            await self.session.commit()
            await self.session.refresh(handoff)
            return handoff
        except IntegrityError:
            await self.session.rollback()
            existing = await self.handoffs.get_active(
                tenant_id=principal.tenant_id, conversation_id=conversation.id
            )
            if existing is None:
                raise
            return existing

    async def get_current(
        self, *, principal: CustomerPrincipal, conversation_id: UUID
    ) -> HandoffRequest:
        conversation = await self._owned_conversation(principal, conversation_id)
        handoff = await self.handoffs.get_latest(
            tenant_id=principal.tenant_id, conversation_id=conversation.id
        )
        if handoff is None:
            self._raise_handoff_not_found()
        return handoff

    async def add_message(
        self,
        *,
        principal: CustomerPrincipal,
        conversation_id: UUID,
        content: str,
        idempotency_key: str | None,
    ) -> MessageResponse:
        self._require_scope(principal, "chat:write")
        conversation = await self._owned_conversation(principal, conversation_id)
        if conversation.status != ConversationStatus.OPEN:
            self._raise_closed()
        if conversation.mode != ConversationMode.HUMAN:
            raise AppError(
                status_code=409,
                code="handoff_not_active",
                title="Human handoff not active",
                detail="Use the AI message endpoint until a human handoff is requested.",
            )
        if idempotency_key:
            existing = await self.conversations.get_idempotent_user_message(
                tenant_id=principal.tenant_id,
                conversation_id=conversation.id,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                return MessageResponse.model_validate(existing)
        try:
            message = await self.handoffs.create_message(
                conversation=conversation,
                sender=MessageSender.USER,
                content=content.strip(),
                idempotency_key=idempotency_key,
            )
            await self.session.commit()
            await self.session.refresh(message)
            return MessageResponse.model_validate(message)
        except IntegrityError:
            await self.session.rollback()
            if not idempotency_key:
                raise
            existing = await self.conversations.get_idempotent_user_message(
                tenant_id=principal.tenant_id,
                conversation_id=conversation.id,
                idempotency_key=idempotency_key,
            )
            if existing is None:
                raise
            return MessageResponse.model_validate(existing)

    async def _owned_conversation(
        self, principal: CustomerPrincipal, conversation_id: UUID
    ) -> Conversation:
        conversation = await self.handoffs.get_owned_conversation(
            tenant_id=principal.tenant_id,
            application_id=principal.application_id,
            external_user_id=principal.external_user_id,
            conversation_id=conversation_id,
        )
        if conversation is None:
            raise AppError(
                status_code=404,
                code="conversation_not_found",
                title="Conversation not found",
                detail="The requested conversation does not belong to the current user.",
            )
        return conversation

    async def _audit_customer(
        self,
        principal: CustomerPrincipal,
        action: str,
        handoff: HandoffRequest,
        request_id: str | None,
    ) -> None:
        await self.audit.add(
            tenant_id=principal.tenant_id,
            actor_type="external_user",
            actor_id=principal.external_user_id,
            action=action,
            resource_type="handoff",
            resource_id=str(handoff.id),
            request_id=request_id,
            details={
                "conversation_id": str(handoff.conversation_id),
                "application_id": str(principal.application_id),
            },
        )

    @staticmethod
    def _require_scope(principal: CustomerPrincipal, scope: str) -> None:
        if scope not in principal.scopes:
            raise AppError(
                status_code=403,
                code="insufficient_scope",
                title="Forbidden",
                detail=f"The customer token does not include {scope}.",
            )

    @staticmethod
    def _summary(messages: list[Message]) -> str:
        labels = {MessageSender.USER: "Customer", MessageSender.AI: "AI"}
        lines = [
            f"{labels[message.sender]}: {message.content.strip()}"
            for message in messages
            if message.sender in labels and message.content.strip()
        ]
        return "\n".join(lines)[-4000:]

    @staticmethod
    def _raise_closed() -> NoReturn:
        raise AppError(
            status_code=409,
            code="conversation_closed",
            title="Conversation closed",
            detail="Messages cannot be added to a closed conversation.",
        )

    @staticmethod
    def _raise_handoff_not_found() -> NoReturn:
        raise AppError(
            status_code=404,
            code="handoff_not_found",
            title="Handoff not found",
            detail="There is no active handoff for this conversation.",
        )


class AgentHandoffService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.handoffs = HandoffRepository(session)
        self.conversations = ConversationRepository(session)
        self.audit = AuditRepository(session)

    async def list_handoffs(
        self, *, actor: StaffPrincipal, status: HandoffStatus | None
    ) -> list[HandoffRequest]:
        tenant_id = self._tenant_id(actor)
        return await self.handoffs.list(tenant_id=tenant_id, status=status)

    async def accept(
        self, *, actor: StaffPrincipal, handoff_id: UUID, request_id: str | None
    ) -> HandoffRequest:
        tenant_id = self._tenant_id(actor)
        handoff = await self.handoffs.accept(
            tenant_id=tenant_id,
            handoff_id=handoff_id,
            staff_user_id=actor.user_id,
        )
        if handoff is None:
            existing = await self.handoffs.get_by_id(tenant_id=tenant_id, handoff_id=handoff_id)
            if existing is None:
                self._raise_handoff_not_found()
            raise AppError(
                status_code=409,
                code="handoff_already_claimed",
                title="Handoff already claimed",
                detail="This handoff is no longer waiting for an agent.",
            )
        await self._audit(actor, "handoff.accept", handoff, request_id)
        await self.session.commit()
        await self.session.refresh(handoff)
        return handoff

    async def add_message(
        self,
        *,
        actor: StaffPrincipal,
        handoff_id: UUID,
        content: str,
        request_id: str | None,
    ) -> MessageResponse:
        tenant_id = self._tenant_id(actor)
        handoff = await self._assigned_handoff(tenant_id, actor.user_id, handoff_id)
        conversation = await self._conversation(tenant_id, handoff.conversation_id)
        if conversation.status != ConversationStatus.OPEN:
            CustomerHandoffService._raise_closed()
        message = await self.handoffs.create_message(
            conversation=conversation,
            sender=MessageSender.AGENT,
            sender_staff_user_id=actor.user_id,
            content=content.strip(),
        )
        await self._audit(actor, "handoff.message", handoff, request_id)
        await self.session.commit()
        await self.session.refresh(message)
        return MessageResponse.model_validate(message)

    async def list_messages(
        self, *, actor: StaffPrincipal, handoff_id: UUID
    ) -> list[MessageResponse]:
        tenant_id = self._tenant_id(actor)
        handoff = await self._get_handoff(tenant_id, handoff_id)
        messages = await self.conversations.list_messages(
            tenant_id=tenant_id, conversation_id=handoff.conversation_id
        )
        return [MessageResponse.model_validate(message) for message in messages]

    async def close(
        self,
        *,
        actor: StaffPrincipal,
        handoff_id: UUID,
        reason: str,
        request_id: str | None,
    ) -> HandoffRequest:
        tenant_id = self._tenant_id(actor)
        handoff = await self._assigned_handoff(tenant_id, actor.user_id, handoff_id)
        conversation = await self._conversation(tenant_id, handoff.conversation_id)
        await self.handoffs.close(
            handoff=handoff,
            conversation=conversation,
            staff_user_id=actor.user_id,
            reason=reason.strip(),
        )
        await self._audit(actor, "handoff.close", handoff, request_id)
        await self.session.commit()
        await self.session.refresh(handoff)
        return handoff

    async def _assigned_handoff(
        self, tenant_id: UUID, staff_user_id: UUID, handoff_id: UUID
    ) -> HandoffRequest:
        handoff = await self._get_handoff(tenant_id, handoff_id)
        if (
            handoff.status != HandoffStatus.ACCEPTED
            or handoff.assigned_staff_user_id != staff_user_id
        ):
            raise AppError(
                status_code=409,
                code="handoff_not_owned",
                title="Handoff not owned",
                detail="Only the assigned agent can reply to or close this handoff.",
            )
        return handoff

    async def _get_handoff(self, tenant_id: UUID, handoff_id: UUID) -> HandoffRequest:
        handoff = await self.handoffs.get_by_id(tenant_id=tenant_id, handoff_id=handoff_id)
        if handoff is None:
            self._raise_handoff_not_found()
        return handoff

    async def _conversation(self, tenant_id: UUID, conversation_id: UUID) -> Conversation:
        conversation = await self.handoffs.get_conversation(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        if conversation is None:
            raise AppError(
                status_code=404,
                code="conversation_not_found",
                title="Conversation not found",
                detail="The handoff conversation no longer exists.",
            )
        return conversation

    async def _audit(
        self,
        actor: StaffPrincipal,
        action: str,
        handoff: HandoffRequest,
        request_id: str | None,
    ) -> None:
        await self.audit.add(
            tenant_id=actor.tenant_id,
            actor_type="staff",
            actor_id=str(actor.user_id),
            action=action,
            resource_type="handoff",
            resource_id=str(handoff.id),
            request_id=request_id,
            details={
                "conversation_id": str(handoff.conversation_id),
                "application_id": str(handoff.application_id),
            },
        )

    @staticmethod
    def _tenant_id(actor: StaffPrincipal) -> UUID:
        assert actor.tenant_id is not None
        return actor.tenant_id

    @staticmethod
    def _raise_handoff_not_found() -> NoReturn:
        CustomerHandoffService._raise_handoff_not_found()
