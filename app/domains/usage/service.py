from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.domains.applications.repository import ApplicationRepository
from app.domains.audit.models import AuditLog
from app.domains.model_gateway.models import AIModelConfig
from app.domains.usage.models import AIUsageRecord
from app.domains.usage.schemas import (
    AuditLogResponse,
    ModelCallResponse,
    UsageSummaryResponse,
)


class UsageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.applications = ApplicationRepository(session)

    async def summary(
        self,
        *,
        tenant_id: UUID,
        from_at: datetime | None,
        to_at: datetime | None,
        application_id: UUID | None,
    ) -> UsageSummaryResponse:
        start, end = self._normalize_range(from_at=from_at, to_at=to_at)
        await self._validate_application(tenant_id=tenant_id, application_id=application_id)
        filters = [
            AIUsageRecord.tenant_id == tenant_id,
            AIUsageRecord.created_at >= start,
            AIUsageRecord.created_at <= end,
        ]
        if application_id is not None:
            filters.append(AIUsageRecord.application_id == application_id)
        statement = select(
            func.count(AIUsageRecord.id),
            func.sum(case((AIUsageRecord.status == "completed", 1), else_=0)),
            func.sum(case((AIUsageRecord.status == "failed", 1), else_=0)),
            func.coalesce(func.sum(AIUsageRecord.prompt_tokens), 0),
            func.coalesce(func.sum(AIUsageRecord.completion_tokens), 0),
            func.coalesce(func.avg(AIUsageRecord.duration_ms), 0),
            func.coalesce(func.sum(AIUsageRecord.estimated_cost_micros), 0),
        ).where(*filters)
        row = (await self.session.execute(statement)).one()
        return UsageSummaryResponse(
            from_at=start,
            to_at=end,
            application_id=application_id,
            total_requests=int(row[0] or 0),
            completed_requests=int(row[1] or 0),
            failed_requests=int(row[2] or 0),
            prompt_tokens=int(row[3] or 0),
            completion_tokens=int(row[4] or 0),
            average_duration_ms=float(row[5] or 0),
            estimated_cost_micros=int(row[6] or 0),
        )

    async def model_calls(
        self,
        *,
        tenant_id: UUID,
        from_at: datetime | None,
        to_at: datetime | None,
        application_id: UUID | None,
        status: str | None,
        limit: int,
    ) -> list[ModelCallResponse]:
        start, end = self._normalize_range(from_at=from_at, to_at=to_at)
        await self._validate_application(tenant_id=tenant_id, application_id=application_id)
        filters = [
            AIUsageRecord.tenant_id == tenant_id,
            AIUsageRecord.created_at >= start,
            AIUsageRecord.created_at <= end,
        ]
        if application_id is not None:
            filters.append(AIUsageRecord.application_id == application_id)
        if status is not None:
            filters.append(AIUsageRecord.status == status)
        statement = (
            select(AIUsageRecord, AIModelConfig.model_name)
            .join(AIModelConfig, AIModelConfig.id == AIUsageRecord.model_config_id)
            .where(*filters)
            .order_by(AIUsageRecord.created_at.desc(), AIUsageRecord.id.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(statement)).all()
        return [
            ModelCallResponse(
                id=record.id,
                application_id=record.application_id,
                conversation_id=record.conversation_id,
                message_id=record.message_id,
                model_config_id=record.model_config_id,
                model_name=model_name,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                duration_ms=record.duration_ms,
                estimated_cost_micros=record.estimated_cost_micros,
                status=record.status,
                error_code=record.error_code,
                created_at=record.created_at,
            )
            for record, model_name in rows
        ]

    async def audit_logs(self, *, tenant_id: UUID, limit: int) -> list[AuditLogResponse]:
        statement = (
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        logs = list(await self.session.scalars(statement))
        return [AuditLogResponse.model_validate(log) for log in logs]

    async def _validate_application(self, *, tenant_id: UUID, application_id: UUID | None) -> None:
        if application_id is None:
            return
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

    @classmethod
    def _normalize_range(
        cls, *, from_at: datetime | None, to_at: datetime | None
    ) -> tuple[datetime, datetime]:
        end = cls._utc(to_at) if to_at else datetime.now(UTC)
        start = cls._utc(from_at) if from_at else end - timedelta(days=30)
        if start > end:
            raise AppError(
                status_code=422,
                code="usage_range_invalid",
                title="Usage range invalid",
                detail="The usage range start must not be later than its end.",
            )
        return start, end

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
