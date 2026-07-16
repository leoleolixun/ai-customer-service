from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.dependencies import SessionDependency, TenantAdminDependency
from app.domains.usage.schemas import (
    AuditLogResponse,
    ModelCallResponse,
    UsageSummaryResponse,
)
from app.domains.usage.service import UsageService

router = APIRouter(prefix="/admin", tags=["tenant-operations"])


@router.get(
    "/usage/summary",
    response_model=UsageSummaryResponse,
    operation_id="getUsageSummary",
)
async def get_usage_summary(
    actor: TenantAdminDependency,
    session: SessionDependency,
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
    application_id: UUID | None = None,
) -> UsageSummaryResponse:
    assert actor.tenant_id is not None
    return await UsageService(session).summary(
        tenant_id=actor.tenant_id,
        from_at=from_at,
        to_at=to_at,
        application_id=application_id,
    )


@router.get(
    "/usage/model-calls",
    response_model=list[ModelCallResponse],
    operation_id="listModelCalls",
)
async def list_model_calls(
    actor: TenantAdminDependency,
    session: SessionDependency,
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
    application_id: UUID | None = None,
    status: Annotated[str | None, Query(pattern="^(completed|failed)$")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ModelCallResponse]:
    assert actor.tenant_id is not None
    return await UsageService(session).model_calls(
        tenant_id=actor.tenant_id,
        from_at=from_at,
        to_at=to_at,
        application_id=application_id,
        status=status,
        limit=limit,
    )


@router.get(
    "/audit-logs",
    response_model=list[AuditLogResponse],
    operation_id="listAuditLogs",
)
async def list_audit_logs(
    actor: TenantAdminDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditLogResponse]:
    assert actor.tenant_id is not None
    return await UsageService(session).audit_logs(tenant_id=actor.tenant_id, limit=limit)
