from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.cache import get_redis
from app.core.storage import get_object_storage
from app.providers.storage.memory import MemoryObjectStorage


class FailingObjectStorage(MemoryObjectStorage):
    async def check_ready(self) -> None:
        raise RuntimeError("internal endpoint")


async def test_health_live_returns_request_id(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


async def test_health_ready_checks_database_redis_and_storage(test_app: FastAPI) -> None:
    redis = AsyncMock()
    redis.ping.return_value = True
    test_app.dependency_overrides[get_redis] = lambda: redis

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://testserver"
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    redis.ping.assert_awaited_once()


async def test_health_ready_hides_dependency_failure(test_app: FastAPI) -> None:
    redis = AsyncMock()
    redis.ping.return_value = True
    test_app.dependency_overrides[get_redis] = lambda: redis
    test_app.dependency_overrides[get_object_storage] = FailingObjectStorage

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://testserver"
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"
    assert "internal endpoint" not in response.text
