from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.conversations.models import (
    Conversation,
    ConversationStatus,
    EndUser,
    Message,
    MessageSender,
    MessageStatus,
)
from app.domains.handoffs.models import HandoffRequest, HandoffStatus


class HandoffRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_owned_conversation(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        external_user_id: str,
        conversation_id: UUID,
    ) -> Conversation | None:
        statement = (
            select(Conversation)
            .join(EndUser, EndUser.id == Conversation.end_user_id)
            .where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.application_id == application_id,
                EndUser.tenant_id == tenant_id,
                EndUser.application_id == application_id,
                EndUser.external_user_id == external_user_id,
            )
        )
        return cast(Conversation | None, await self.session.scalar(statement))

    async def get_conversation(
        self, *, tenant_id: UUID, conversation_id: UUID
    ) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
        )
        return cast(Conversation | None, await self.session.scalar(statement))

    async def get_active(self, *, tenant_id: UUID, conversation_id: UUID) -> HandoffRequest | None:
        statement = select(HandoffRequest).where(
            HandoffRequest.tenant_id == tenant_id,
            HandoffRequest.conversation_id == conversation_id,
            HandoffRequest.status.in_([HandoffStatus.PENDING, HandoffStatus.ACCEPTED]),
        )
        return cast(HandoffRequest | None, await self.session.scalar(statement))

    async def get_latest(self, *, tenant_id: UUID, conversation_id: UUID) -> HandoffRequest | None:
        statement = (
            select(HandoffRequest)
            .where(
                HandoffRequest.tenant_id == tenant_id,
                HandoffRequest.conversation_id == conversation_id,
            )
            .order_by(HandoffRequest.created_at.desc(), HandoffRequest.id.desc())
            .limit(1)
        )
        return cast(HandoffRequest | None, await self.session.scalar(statement))

    async def create(
        self, *, conversation: Conversation, reason: str, summary: str
    ) -> HandoffRequest:
        handoff = HandoffRequest(
            tenant_id=conversation.tenant_id,
            application_id=conversation.application_id,
            conversation_id=conversation.id,
            requested_by_end_user_id=conversation.end_user_id,
            reason=reason,
            summary=summary,
        )
        self.session.add(handoff)
        await self.session.flush()
        return handoff

    async def get_by_id(self, *, tenant_id: UUID, handoff_id: UUID) -> HandoffRequest | None:
        statement = select(HandoffRequest).where(
            HandoffRequest.id == handoff_id,
            HandoffRequest.tenant_id == tenant_id,
        )
        return cast(HandoffRequest | None, await self.session.scalar(statement))

    async def list(self, *, tenant_id: UUID, status: HandoffStatus | None) -> list[HandoffRequest]:
        statement = select(HandoffRequest).where(HandoffRequest.tenant_id == tenant_id)
        if status is not None:
            statement = statement.where(HandoffRequest.status == status)
        statement = statement.order_by(HandoffRequest.created_at, HandoffRequest.id)
        return list(await self.session.scalars(statement))

    async def accept(
        self, *, tenant_id: UUID, handoff_id: UUID, staff_user_id: UUID
    ) -> HandoffRequest | None:
        statement = (
            update(HandoffRequest)
            .where(
                HandoffRequest.id == handoff_id,
                HandoffRequest.tenant_id == tenant_id,
                HandoffRequest.status == HandoffStatus.PENDING,
            )
            .values(
                status=HandoffStatus.ACCEPTED,
                assigned_staff_user_id=staff_user_id,
                accepted_at=datetime.now(UTC),
            )
            .returning(HandoffRequest)
        )
        return cast(HandoffRequest | None, await self.session.scalar(statement))

    async def create_message(
        self,
        *,
        conversation: Conversation,
        sender: MessageSender,
        content: str,
        sender_staff_user_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> Message:
        message = Message(
            tenant_id=conversation.tenant_id,
            application_id=conversation.application_id,
            conversation_id=conversation.id,
            sender=sender,
            sender_staff_user_id=sender_staff_user_id,
            content=content,
            status=MessageStatus.COMPLETED,
            idempotency_key=idempotency_key,
            created_at=datetime.now(UTC),
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def close(
        self,
        *,
        handoff: HandoffRequest,
        conversation: Conversation,
        staff_user_id: UUID,
        reason: str,
    ) -> None:
        handoff.status = HandoffStatus.CLOSED
        handoff.closed_by_staff_user_id = staff_user_id
        handoff.closed_at = datetime.now(UTC)
        handoff.close_reason = reason
        conversation.status = ConversationStatus.CLOSED
        await self.session.flush()
