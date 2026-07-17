from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.core.cache import get_redis
from app.core.database import async_session_factory, engine
from app.core.errors import AppError
from app.core.rate_limit import RedisRateLimiter
from app.core.storage import get_object_storage
from app.domains.applications.models import Application
from app.domains.knowledge.models import (
    IngestionJob,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.domains.knowledge.parsing import lexicalize
from app.domains.knowledge.repository import KnowledgeRepository
from app.domains.knowledge.service import IngestionService
from app.domains.tenants.models import Tenant
from app.providers.llm.fake import FakeEmbeddingProvider


@dataclass(frozen=True, slots=True)
class TenantFixture:
    tenant_id: UUID
    application_id: UUID
    base_id: UUID
    document_id: UUID
    object_key: str
    content: str
    document_status: str
    job_status: str
    chunk_count: int


async def load_fixture(slug: str) -> TenantFixture:
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(Tenant, Application, KnowledgeBase, KnowledgeDocument, IngestionJob)
                .join(Application, Application.tenant_id == Tenant.id)
                .join(KnowledgeBase, KnowledgeBase.tenant_id == Tenant.id)
                .join(KnowledgeDocument, KnowledgeDocument.knowledge_base_id == KnowledgeBase.id)
                .join(IngestionJob, IngestionJob.document_id == KnowledgeDocument.id)
                .where(
                    Tenant.slug == slug,
                    KnowledgeBase.name == "V1 evaluation corpus",
                )
                .order_by(Application.id, KnowledgeDocument.id)
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError(f"seeded fixture is missing for {slug}")
        tenant, application, knowledge_base, document, job = row
        chunk = await session.scalar(
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.tenant_id == tenant.id,
                KnowledgeChunk.document_id == document.id,
            )
            .order_by(KnowledgeChunk.chunk_index)
            .limit(1)
        )
        if chunk is None:
            raise RuntimeError(f"seeded document has no chunk for {slug}")
        chunk_count = int(
            await session.scalar(
                select(func.count(KnowledgeChunk.id)).where(
                    KnowledgeChunk.tenant_id == tenant.id,
                    KnowledgeChunk.document_id == document.id,
                )
            )
            or 0
        )
        return TenantFixture(
            tenant_id=tenant.id,
            application_id=application.id,
            base_id=knowledge_base.id,
            document_id=document.id,
            object_key=document.object_key,
            content=chunk.content,
            document_status=document.status.value,
            job_status=job.status.value,
            chunk_count=chunk_count,
        )


async def verify_vector_isolation(left: TenantFixture, right: TenantFixture) -> dict[str, Any]:
    vector = (
        await FakeEmbeddingProvider().embed(
            texts=[left.content], model="fake-embedding", dimensions=32
        )
    )[0]
    lexical_query = lexicalize(left.content)
    async with async_session_factory() as session:
        repository = KnowledgeRepository(session)
        own_results = await repository.search(
            tenant_id=left.tenant_id,
            base_id=left.base_id,
            query_vector=vector,
            lexical_query=lexical_query,
            limit=20,
            keyword_score_threshold=0,
            vector_similarity_threshold=0,
        )
        cross_results = await repository.search(
            tenant_id=right.tenant_id,
            base_id=left.base_id,
            query_vector=vector,
            lexical_query=lexical_query,
            limit=20,
            keyword_score_threshold=0,
            vector_similarity_threshold=0,
        )
    if not own_results:
        raise RuntimeError("tenant-scoped vector search returned no seeded result")
    if any(result.document.tenant_id != left.tenant_id for result in own_results):
        raise RuntimeError("tenant-scoped vector search returned another tenant's document")
    if cross_results:
        raise RuntimeError("a tenant could search another tenant's knowledge base")
    return {"own_results": len(own_results), "cross_tenant_results": len(cross_results)}


async def verify_object_isolation(left: TenantFixture, right: TenantFixture) -> dict[str, Any]:
    storage = get_object_storage()
    expected_prefix = f"tenants/{left.tenant_id}/knowledge/"
    if not left.object_key.startswith(expected_prefix):
        raise RuntimeError("the stored object key is not tenant-prefixed")
    content = await storage.get(left.object_key)
    if not content:
        raise RuntimeError("the seeded tenant object is empty")
    wrong_key = left.object_key.replace(
        f"tenants/{left.tenant_id}/", f"tenants/{right.tenant_id}/", 1
    )
    try:
        await storage.get(wrong_key)
    except AppError as exc:
        if exc.code != "object_storage_read_failed":
            raise
    else:
        raise RuntimeError("another tenant prefix resolved the source object")
    return {"tenant_prefix": expected_prefix, "cross_tenant_read": "rejected"}


async def verify_redis_isolation(left: TenantFixture, right: TenantFixture) -> dict[str, Any]:
    redis = get_redis()
    marker = f"component-isolation:{uuid4()}"
    limiter = RedisRateLimiter(redis)
    created_keys: list[str] = []
    try:
        await limiter.check(
            tenant_id=left.tenant_id,
            application_id=left.application_id,
            subject=marker,
            limit=10,
        )
        await limiter.check(
            tenant_id=right.tenant_id,
            application_id=right.application_id,
            subject=marker,
            limit=10,
        )
        for fixture in (left, right):
            pattern = f"rate:v1:{fixture.tenant_id}:{fixture.application_id}:*"
            matches = [str(key) async for key in redis.scan_iter(match=pattern)]
            if len(matches) != 1:
                raise RuntimeError(
                    f"expected one isolated Redis key for {fixture.tenant_id}, found {len(matches)}"
                )
            created_keys.extend(matches)
        if len(set(created_keys)) != 2:
            raise RuntimeError("the two tenants shared a Redis rate-limit key")
        return {"isolated_keys": len(created_keys), "shared_keys": 0}
    finally:
        if created_keys:
            await redis.delete(*created_keys)


async def verify_task_isolation(left: TenantFixture, right: TenantFixture) -> dict[str, Any]:
    storage = get_object_storage()
    async with async_session_factory() as session:
        try:
            await IngestionService(session, storage).process(
                tenant_id=right.tenant_id,
                document_id=left.document_id,
            )
        except AppError as exc:
            if exc.code != "ingestion_context_not_found":
                raise
        else:
            raise RuntimeError("the ingestion entry point accepted another tenant's document")

    current = await load_fixture_by_document(left.document_id)
    if (
        current.document_status != left.document_status
        or current.job_status != left.job_status
        or current.chunk_count != left.chunk_count
    ):
        raise RuntimeError("the rejected cross-tenant task changed persisted document state")
    return {"cross_tenant_task": "rejected", "persisted_state_changed": False}


async def load_fixture_by_document(document_id: UUID) -> TenantFixture:
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(Tenant, Application, KnowledgeBase, KnowledgeDocument, IngestionJob)
                .join(Application, Application.tenant_id == Tenant.id)
                .join(KnowledgeBase, KnowledgeBase.tenant_id == Tenant.id)
                .join(KnowledgeDocument, KnowledgeDocument.knowledge_base_id == KnowledgeBase.id)
                .join(IngestionJob, IngestionJob.document_id == KnowledgeDocument.id)
                .where(KnowledgeDocument.id == document_id)
                .order_by(Application.id)
                .limit(1)
            )
        ).one()
        tenant, application, knowledge_base, document, job = row
        chunk = await session.scalar(
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.tenant_id == tenant.id,
                KnowledgeChunk.document_id == document.id,
            )
            .order_by(KnowledgeChunk.chunk_index)
            .limit(1)
        )
        chunk_count = int(
            await session.scalar(
                select(func.count(KnowledgeChunk.id)).where(
                    KnowledgeChunk.tenant_id == tenant.id,
                    KnowledgeChunk.document_id == document.id,
                )
            )
            or 0
        )
        return TenantFixture(
            tenant_id=tenant.id,
            application_id=application.id,
            base_id=knowledge_base.id,
            document_id=document.id,
            object_key=document.object_key,
            content=chunk.content if chunk is not None else "",
            document_status=document.status.value,
            job_status=job.status.value,
            chunk_count=chunk_count,
        )


async def run() -> dict[str, Any]:
    left = await load_fixture("demo-retail")
    right = await load_fixture("demo-saas")
    try:
        return {
            "passed": True,
            "tenants": [str(left.tenant_id), str(right.tenant_id)],
            "postgres_pgvector": await verify_vector_isolation(left, right),
            "minio": await verify_object_isolation(left, right),
            "redis": await verify_redis_isolation(left, right),
            "worker_entrypoint": await verify_task_isolation(left, right),
        }
    finally:
        await get_redis().aclose()
        await engine.dispose()


def main() -> None:
    try:
        report = asyncio.run(run())
    except (AppError, RuntimeError, OSError, ValueError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
