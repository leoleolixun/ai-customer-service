import asyncio
import hashlib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.core.storage import get_object_storage
from app.domains.knowledge.service import DocumentService, IngestionService
from app.workers.celery_app import celery_app


@celery_app.task(
    name="knowledge.ingest_document",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)  # type: ignore[untyped-decorator]
def ingest_knowledge_document(tenant_id: str, document_id: str) -> None:
    asyncio.run(_ingest(UUID(tenant_id), UUID(document_id)))


@celery_app.task(name="knowledge.cleanup_deleted_objects")  # type: ignore[untyped-decorator]
def cleanup_deleted_knowledge_objects() -> dict[str, int]:
    return asyncio.run(_cleanup_deleted_objects())


async def _cleanup_deleted_objects() -> dict[str, int]:
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await DocumentService(session, get_object_storage()).cleanup_pending_objects()
    finally:
        await engine.dispose()


async def _ingest(tenant_id: UUID, document_id: UUID) -> None:
    try:
        async with engine.connect() as connection:
            lock_id = _document_lock_id(tenant_id, document_id)
            if connection.dialect.name == "postgresql":
                await connection.execute(
                    text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": lock_id}
                )
                await connection.commit()
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    await IngestionService(session, get_object_storage()).process(
                        tenant_id=tenant_id,
                        document_id=document_id,
                    )
            finally:
                if connection.dialect.name == "postgresql":
                    await connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id}
                    )
                    await connection.commit()
    finally:
        # Celery executes this async task through a fresh event loop.
        # Disposing prevents pooled asyncpg connections crossing event loops.
        await engine.dispose()


def _document_lock_id(tenant_id: UUID, document_id: UUID) -> int:
    digest = hashlib.sha256(tenant_id.bytes + document_id.bytes).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=True)
