from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        tenant_id: UUID | None,
        actor_type: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None,
        request_id: str | None,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            tenant_id=tenant_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id,
            details=details or {},
        )
        self.session.add(entry)
        await self.session.flush()
        return entry
