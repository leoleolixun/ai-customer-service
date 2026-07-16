import hashlib
import hmac
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.cache import get_redis
from app.core.config import get_settings
from app.core.errors import AppError


def _rate_limit_key(
    *,
    tenant_id: UUID,
    application_id: UUID,
    subject: str,
    window: int,
) -> str:
    pepper = get_settings().credential_pepper.get_secret_value().encode()
    subject_digest = hmac.new(pepper, subject.encode(), hashlib.sha256).hexdigest()
    return f"rate:v1:{tenant_id}:{application_id}:{subject_digest}:{window}"


class RateLimiter(Protocol):
    async def check(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        subject: str,
        limit: int,
    ) -> None: ...


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def check(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        subject: str,
        limit: int,
    ) -> None:
        now = datetime.now(UTC)
        window = int(now.timestamp()) // 60
        key = _rate_limit_key(
            tenant_id=tenant_id,
            application_id=application_id,
            subject=subject,
            window=window,
        )
        try:
            pipeline = self.redis.pipeline(transaction=True)
            pipeline.incr(key)
            pipeline.expire(key, 120)
            count, _ = await pipeline.execute()
        except RedisError as exc:
            raise AppError(
                status_code=503,
                code="rate_limiter_unavailable",
                title="Rate limiter unavailable",
                detail="Customer requests are temporarily unavailable.",
            ) from exc
        if int(count) > limit:
            retry_after = 60 - (int(now.timestamp()) % 60)
            raise AppError(
                status_code=429,
                code="rate_limit_exceeded",
                title="Rate limit exceeded",
                detail="Too many requests were sent for this application user.",
                extra={"retry_after_seconds": retry_after},
                headers={"Retry-After": str(retry_after)},
            )


class MemoryRateLimiter:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def check(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        subject: str,
        limit: int,
    ) -> None:
        window = int(datetime.now(UTC).timestamp()) // 60
        key = _rate_limit_key(
            tenant_id=tenant_id,
            application_id=application_id,
            subject=subject,
            window=window,
        )
        self.counts[key] = self.counts.get(key, 0) + 1
        if self.counts[key] > limit:
            raise AppError(
                status_code=429,
                code="rate_limit_exceeded",
                title="Rate limit exceeded",
                detail="Too many requests were sent for this application user.",
                extra={"retry_after_seconds": 60},
                headers={"Retry-After": "60"},
            )


@lru_cache
def get_rate_limiter() -> RateLimiter:
    return RedisRateLimiter(get_redis())
