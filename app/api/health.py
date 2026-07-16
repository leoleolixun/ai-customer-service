from typing import Annotated

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis
from app.core.database import get_db_session
from app.core.errors import AppError
from app.core.storage import get_object_storage
from app.providers.storage.base import ObjectStorage

router = APIRouter(tags=["health"])


@router.get("/health/live", operation_id="healthLive")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", operation_id="healthReady")
async def ready(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
        await redis.ping()
        await storage.check_ready()
    except Exception as exc:
        raise AppError(
            status_code=503,
            code="dependency_unavailable",
            title="Service unavailable",
            detail="A required dependency is unavailable.",
        ) from exc
    return {"status": "ready"}
