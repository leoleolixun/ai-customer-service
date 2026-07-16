from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import get_db_session
from app.core.rate_limit import MemoryRateLimiter, get_rate_limiter
from app.core.storage import get_object_storage
from app.infrastructure.database.base import Base
from app.main import create_app
from app.providers.storage.memory import MemoryObjectStorage


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def memory_storage() -> MemoryObjectStorage:
    return MemoryObjectStorage()


@pytest.fixture
def memory_rate_limiter() -> MemoryRateLimiter:
    return MemoryRateLimiter()


@pytest.fixture
def test_app(
    session_factory: async_sessionmaker[AsyncSession],
    memory_storage: MemoryObjectStorage,
    memory_rate_limiter: MemoryRateLimiter,
) -> FastAPI:
    application = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_db_session] = override_session
    application.dependency_overrides[get_object_storage] = lambda: memory_storage
    application.dependency_overrides[get_rate_limiter] = lambda: memory_rate_limiter
    return application


@pytest_asyncio.fixture
async def client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
