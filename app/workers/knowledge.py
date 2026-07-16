import asyncio
from uuid import UUID

from app.core.database import async_session_factory, engine
from app.core.storage import get_object_storage
from app.domains.knowledge.service import IngestionService
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


async def _ingest(tenant_id: UUID, document_id: UUID) -> None:
    try:
        async with async_session_factory() as session:
            await IngestionService(session, get_object_storage()).process(
                tenant_id=tenant_id,
                document_id=document_id,
            )
    finally:
        # Celery executes this async task through a fresh event loop.
        # Disposing prevents pooled asyncpg connections crossing event loops.
        await engine.dispose()
