from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.conversations.models import (
    Conversation,
    ConversationFeedback,
    ConversationMode,
    ConversationStatus,
    EndUser,
    FeedbackRating,
    Message,
    MessageSender,
    MessageStatus,
)
from app.domains.usage.models import AIUsageRecord


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_end_user(
        self, *, tenant_id: UUID, application_id: UUID, external_user_id: str
    ) -> EndUser:
        statement = select(EndUser).where(
            EndUser.tenant_id == tenant_id,
            EndUser.application_id == application_id,
            EndUser.external_user_id == external_user_id,
        )
        user = cast(EndUser | None, await self.session.scalar(statement))
        if user is None:
            user = EndUser(
                tenant_id=tenant_id,
                application_id=application_id,
                external_user_id=external_user_id,
            )
            self.session.add(user)
            await self.session.flush()
        return user

    async def create_conversation(
        self, *, tenant_id: UUID, application_id: UUID, end_user_id: UUID
    ) -> Conversation:
        conversation = Conversation(
            tenant_id=tenant_id,
            application_id=application_id,
            end_user_id=end_user_id,
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

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

    async def get_conversation_state(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        for_update: bool = False,
    ) -> tuple[ConversationMode, ConversationStatus] | None:
        statement = select(Conversation.mode, Conversation.status).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    async def list_messages(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        limit: int = 100,
        before: Message | None = None,
    ) -> list[Message]:
        statement = (
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        if before is not None:
            statement = statement.where(
                or_(
                    Message.created_at < before.created_at,
                    and_(Message.created_at == before.created_at, Message.id < before.id),
                )
            )
        messages = list(await self.session.scalars(statement))
        messages.reverse()
        return messages

    async def get_message_cursor(
        self, *, tenant_id: UUID, conversation_id: UUID, message_id: UUID
    ) -> Message | None:
        statement = select(Message).where(
            Message.id == message_id,
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation_id,
        )
        return cast(Message | None, await self.session.scalar(statement))

    async def get_recent_completed_messages(
        self, *, tenant_id: UUID, conversation_id: UUID, limit: int = 20
    ) -> list[Message]:
        statement = (
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.status == MessageStatus.COMPLETED,
                Message.sender.in_([MessageSender.USER, MessageSender.AI]),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        messages = list(await self.session.scalars(statement))
        messages.reverse()
        return messages

    async def get_idempotent_user_message(
        self, *, tenant_id: UUID, conversation_id: UUID, idempotency_key: str
    ) -> Message | None:
        statement = select(Message).where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation_id,
            Message.idempotency_key == idempotency_key,
            Message.sender == MessageSender.USER,
        )
        return cast(Message | None, await self.session.scalar(statement))

    async def get_reply(self, *, tenant_id: UUID, user_message_id: UUID) -> Message | None:
        statement = select(Message).where(
            Message.tenant_id == tenant_id,
            Message.reply_to_message_id == user_message_id,
            Message.sender == MessageSender.AI,
        )
        return cast(Message | None, await self.session.scalar(statement))

    async def get_feedback_target(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
    ) -> Message | None:
        statement = select(Message).where(
            Message.id == message_id,
            Message.tenant_id == tenant_id,
            Message.application_id == application_id,
            Message.conversation_id == conversation_id,
            Message.sender.in_([MessageSender.AI, MessageSender.AGENT]),
            Message.status == MessageStatus.COMPLETED,
        )
        return cast(Message | None, await self.session.scalar(statement))

    async def upsert_feedback(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        conversation_id: UUID,
        end_user_id: UUID,
        message_id: UUID,
        rating: FeedbackRating,
        comment: str | None,
    ) -> ConversationFeedback:
        statement = select(ConversationFeedback).where(
            ConversationFeedback.tenant_id == tenant_id,
            ConversationFeedback.message_id == message_id,
        )
        feedback = cast(ConversationFeedback | None, await self.session.scalar(statement))
        if feedback is None:
            feedback = ConversationFeedback(
                tenant_id=tenant_id,
                application_id=application_id,
                conversation_id=conversation_id,
                end_user_id=end_user_id,
                message_id=message_id,
                rating=rating,
                comment=comment,
            )
            self.session.add(feedback)
        else:
            feedback.rating = rating
            feedback.comment = comment
        await self.session.flush()
        return feedback

    async def list_feedback(
        self, *, tenant_id: UUID, limit: int
    ) -> list[tuple[ConversationFeedback, str]]:
        statement = (
            select(ConversationFeedback, Message.content)
            .join(
                Message,
                (Message.id == ConversationFeedback.message_id)
                & (Message.tenant_id == ConversationFeedback.tenant_id),
            )
            .where(ConversationFeedback.tenant_id == tenant_id)
            .order_by(ConversationFeedback.created_at.desc(), ConversationFeedback.id.desc())
            .limit(limit)
        )
        rows = await self.session.execute(statement)
        return [(feedback, content) for feedback, content in rows.all()]

    async def create_message_pair(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        conversation_id: UUID,
        content: str,
        idempotency_key: str | None,
        model_config_id: UUID,
    ) -> tuple[Message, Message]:
        created_at = datetime.now(UTC)
        user_message = Message(
            tenant_id=tenant_id,
            application_id=application_id,
            conversation_id=conversation_id,
            sender=MessageSender.USER,
            content=content,
            status=MessageStatus.COMPLETED,
            idempotency_key=idempotency_key,
            created_at=created_at,
        )
        self.session.add(user_message)
        await self.session.flush()
        assistant_message = Message(
            tenant_id=tenant_id,
            application_id=application_id,
            conversation_id=conversation_id,
            reply_to_message_id=user_message.id,
            sender=MessageSender.AI,
            content="",
            status=MessageStatus.GENERATING,
            model_config_id=model_config_id,
            created_at=created_at + timedelta(microseconds=1),
        )
        self.session.add(assistant_message)
        await self.session.flush()
        return user_message, assistant_message

    async def complete_assistant_message(
        self, message: Message, *, content: str, model_info: dict[str, object]
    ) -> None:
        message.content = content
        message.status = MessageStatus.COMPLETED
        message.error_code = None
        message.model_info = model_info
        await self.session.flush()

    async def fail_assistant_message(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
        error_code: str,
    ) -> None:
        statement = (
            update(Message)
            .where(
                Message.id == message_id,
                Message.tenant_id == tenant_id,
                Message.sender == MessageSender.AI,
                Message.status == MessageStatus.GENERATING,
            )
            .values(status=MessageStatus.FAILED, error_code=error_code)
        )
        await self.session.execute(statement)

    async def add_usage(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        model_config_id: UUID,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: int,
        estimated_cost_micros: int,
        status: str,
        error_code: str | None = None,
    ) -> AIUsageRecord:
        record = AIUsageRecord(
            tenant_id=tenant_id,
            application_id=application_id,
            conversation_id=conversation_id,
            message_id=message_id,
            model_config_id=model_config_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
            estimated_cost_micros=estimated_cost_micros,
            status=status,
            error_code=error_code,
        )
        self.session.add(record)
        await self.session.flush()
        return record
