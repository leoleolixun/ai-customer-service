from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, select

from app.core.database import async_session_factory, engine
from app.core.security import (
    CustomerPrincipal,
    StaffPrincipal,
    create_admin_access_token,
    create_customer_token,
    staff_auth_version,
)
from app.domains.applications.models import Application
from app.domains.identities.models import StaffUser, TenantMembership, TenantRole
from app.domains.knowledge.models import (
    DocumentStatus,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.domains.knowledge.parsing import lexicalize
from app.domains.knowledge.service import KnowledgeBaseService
from app.domains.model_gateway.models import AIModelConfig, ModelPurpose
from app.domains.tenants.models import Tenant
from app.providers.llm.fake import FakeEmbeddingProvider

PERFORMANCE_BASE_NAME = "V1 performance corpus"
RETRIEVAL_P95_LIMIT_MS = 500.0
API_P95_LIMIT_MS = 300.0


@dataclass(frozen=True, slots=True)
class TenantTarget:
    tenant_id: UUID
    tenant_slug: str
    application_id: UUID
    application_name: str
    question: str


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        raise ValueError("at least one sample is required")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return round(ordered[index], 3)


def parse_completed_sse(payload: str) -> dict[str, Any]:
    completed: dict[str, Any] | None = None
    for block in payload.split("\n\n"):
        lines = block.splitlines()
        event = next((line[7:] for line in lines if line.startswith("event: ")), "")
        data = next((line[6:] for line in lines if line.startswith("data: ")), "")
        if event == "message.error":
            raise RuntimeError(f"SSE returned message.error: {data}")
        if event == "message.completed" and data:
            value = json.loads(data)
            if not isinstance(value, dict):
                raise RuntimeError("message.completed data must be an object")
            completed = value
    if completed is None:
        raise RuntimeError("SSE response did not contain message.completed")
    return completed


async def prepare_performance_corpus(chunk_count: int) -> UUID:
    async with async_session_factory() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == "demo-retail"))
        if tenant is None:
            raise RuntimeError("Run scripts/seed_demo.py before preparing the performance corpus.")
        model = await session.scalar(
            select(AIModelConfig).where(
                AIModelConfig.tenant_id == tenant.id,
                AIModelConfig.purpose == ModelPurpose.EMBEDDING,
                AIModelConfig.name == "Demo embedding",
            )
        )
        if model is None or model.embedding_dimension is None:
            raise RuntimeError("The demo-retail embedding model is missing.")
        knowledge_base = await session.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.tenant_id == tenant.id,
                KnowledgeBase.name == PERFORMANCE_BASE_NAME,
            )
        )
        if knowledge_base is not None:
            existing_count = int(
                await session.scalar(
                    select(func.count(KnowledgeChunk.id)).where(
                        KnowledgeChunk.tenant_id == tenant.id,
                        KnowledgeChunk.knowledge_base_id == knowledge_base.id,
                    )
                )
                or 0
            )
            if existing_count != chunk_count:
                raise RuntimeError(
                    f"Performance corpus already contains {existing_count} chunks; "
                    f"requested {chunk_count}. Use a clean development database."
                )
            return knowledge_base.id

        knowledge_base = KnowledgeBase(
            tenant_id=tenant.id,
            name=PERFORMANCE_BASE_NAME,
            description="Synthetic local-only data for repeatable V1 performance checks.",
            embedding_model_config_id=model.id,
            embedding_model_name=model.model_name,
            embedding_dimension=model.embedding_dimension,
            embedding_version="performance-v1",
        )
        session.add(knowledge_base)
        await session.flush()
        document = KnowledgeDocument(
            tenant_id=tenant.id,
            knowledge_base_id=knowledge_base.id,
            supersedes_document_id=None,
            version=1,
            title="Synthetic performance topics",
            source_filename="performance-fixture.txt",
            source_url="https://performance.invalid/v1/corpus",
            mime_type="text/plain",
            byte_size=chunk_count * 128,
            object_key=f"performance/{knowledge_base.id}/fixture.txt",
            content_hash=hashlib.sha256(f"performance:{chunk_count}".encode()).hexdigest(),
            status=DocumentStatus.READY,
            error_message=None,
        )
        session.add(document)
        await session.flush()

        provider = FakeEmbeddingProvider()
        batch_size = 500
        for start in range(0, chunk_count, batch_size):
            indexes = range(start, min(start + batch_size, chunk_count))
            contents = [
                (
                    f"性能主题 {index:05d} 的服务窗口是工作日 09:00 至 18:00。"
                    f"该主题的稳定校验编号为 PERF-{index:05d}。"
                )
                for index in indexes
            ]
            embeddings = await provider.embed(
                texts=contents,
                model=model.model_name,
                dimensions=model.embedding_dimension,
            )
            session.add_all(
                [
                    KnowledgeChunk(
                        tenant_id=tenant.id,
                        knowledge_base_id=knowledge_base.id,
                        document_id=document.id,
                        document_version=1,
                        chunk_index=index,
                        content=content,
                        heading_path=["Synthetic performance topics"],
                        lexical_text=lexicalize(content),
                        lexical_vector=lexicalize(content),
                        content_hash=hashlib.sha256(content.encode()).hexdigest(),
                        embedding=embedding,
                        embedding_model=model.model_name,
                        embedding_version="performance-v1",
                        chunking_version="performance-v1",
                    )
                    for index, content, embedding in zip(indexes, contents, embeddings, strict=True)
                ]
            )
            await session.commit()
        return knowledge_base.id


async def benchmark_retrieval(base_id: UUID, request_count: int) -> dict[str, Any]:
    durations: list[float] = []
    async with async_session_factory() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == "demo-retail"))
        if tenant is None:
            raise RuntimeError("demo-retail is missing")
        service = KnowledgeBaseService(session)
        for index in range(request_count):
            query = f"性能主题 {index % 997:05d} 的服务窗口和校验编号是什么?"
            started = perf_counter()
            results = await service.search(
                tenant_id=tenant.id,
                base_id=base_id,
                query=query,
                top_k=5,
            )
            durations.append((perf_counter() - started) * 1000)
            if not results:
                raise RuntimeError("retrieval returned no result")
    p95 = percentile(durations, 0.95)
    return {
        "requests": request_count,
        "p50_ms": percentile(durations, 0.50),
        "p95_ms": p95,
        "max_ms": round(max(durations), 3),
        "limit_ms": RETRIEVAL_P95_LIMIT_MS,
        "passed": p95 < RETRIEVAL_P95_LIMIT_MS,
    }


async def load_targets() -> tuple[list[TenantTarget], str]:
    definitions = (
        ("demo-retail", "storefront-web", "会员积分多久过期?"),
        ("demo-saas", "help-center-web", "新工作区可以试用多久?"),
    )
    targets: list[TenantTarget] = []
    async with async_session_factory() as session:
        for tenant_slug, application_name, question in definitions:
            tenant = await session.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
            if tenant is None:
                raise RuntimeError(f"Seeded tenant is missing: {tenant_slug}")
            application = await session.scalar(
                select(Application).where(
                    Application.tenant_id == tenant.id,
                    Application.name == application_name,
                )
            )
            if application is None:
                raise RuntimeError(f"Seeded application is missing: {application_name}")
            targets.append(
                TenantTarget(
                    tenant_id=tenant.id,
                    tenant_slug=tenant_slug,
                    application_id=application.id,
                    application_name=application_name,
                    question=question,
                )
            )

        retail = targets[0]
        staff_row = (
            await session.execute(
                select(StaffUser, TenantMembership)
                .join(
                    TenantMembership,
                    TenantMembership.staff_user_id == StaffUser.id,
                )
                .where(
                    TenantMembership.tenant_id == retail.tenant_id,
                    TenantMembership.role == TenantRole.TENANT_ADMIN,
                )
            )
        ).first()
        if staff_row is None:
            raise RuntimeError("demo-retail tenant administrator is missing")
        staff, membership = staff_row
        admin_token, _ = create_admin_access_token(
            StaffPrincipal(
                user_id=staff.id,
                email=staff.email,
                is_platform_admin=staff.is_platform_admin,
                tenant_id=retail.tenant_id,
                role=membership.role,
                auth_version=staff_auth_version(staff.password_hash),
            )
        )
    return targets, admin_token


async def benchmark_api(
    client: httpx.AsyncClient, admin_token: str, request_count: int
) -> dict[str, Any]:
    durations: list[float] = []
    headers = {"Authorization": f"Bearer {admin_token}"}
    for _ in range(request_count):
        started = perf_counter()
        response = await client.get("/v1/admin/applications", headers=headers)
        durations.append((perf_counter() - started) * 1000)
        response.raise_for_status()
    p95 = percentile(durations, 0.95)
    return {
        "route": "GET /v1/admin/applications",
        "requests": request_count,
        "p50_ms": percentile(durations, 0.50),
        "p95_ms": p95,
        "max_ms": round(max(durations), 3),
        "limit_ms": API_P95_LIMIT_MS,
        "passed": p95 < API_P95_LIMIT_MS,
    }


async def run_sse_case(
    client: httpx.AsyncClient,
    target: TenantTarget,
    index: int,
) -> dict[str, Any]:
    marker = f"perf-sse-{index:03d}-{uuid4().hex[:8]}"
    principal = CustomerPrincipal(
        tenant_id=target.tenant_id,
        application_id=target.application_id,
        external_user_id=marker,
        scopes=("chat:read", "chat:write", "handoff:create"),
        token_id=uuid4(),
    )
    token, _ = create_customer_token(principal)
    headers = {"Authorization": f"Bearer {token}"}
    session_response = await client.post("/v1/chat/sessions", headers=headers, json={})
    session_response.raise_for_status()
    conversation_id = str(session_response.json()["id"])
    started = perf_counter()
    response = await client.post(
        f"/v1/chat/sessions/{conversation_id}/messages",
        headers={**headers, "Idempotency-Key": marker},
        json={"content": f"{target.question} tracking {marker}"},
    )
    duration_ms = (perf_counter() - started) * 1000
    response.raise_for_status()
    completed = parse_completed_sse(response.text)
    content = str(completed.get("content", ""))
    citations = completed.get("citations", [])
    if marker not in content:
        raise RuntimeError(f"SSE response lost its marker: {marker}")
    for citation in citations:
        source_url = citation.get("source_url") if isinstance(citation, dict) else None
        host = urlsplit(str(source_url)).hostname if source_url else None
        if host != f"{target.tenant_slug}.example.com":
            raise RuntimeError(f"Cross-tenant or unknown citation for {marker}: {source_url!r}")
    return {
        "marker": marker,
        "tenant": target.tenant_slug,
        "conversation_id": conversation_id,
        "message_id": str(completed.get("id", "")),
        "duration_ms": duration_ms,
        "content": content,
    }


async def benchmark_sse(
    client: httpx.AsyncClient,
    targets: list[TenantTarget],
    concurrency: int,
) -> dict[str, Any]:
    results = await asyncio.gather(
        *(
            run_sse_case(client, targets[index % len(targets)], index)
            for index in range(concurrency)
        )
    )
    markers = {str(result["marker"]) for result in results}
    conversation_ids = {str(result["conversation_id"]) for result in results}
    message_ids = {str(result["message_id"]) for result in results}
    for result in results:
        foreign_markers = markers - {str(result["marker"])}
        if any(marker in str(result["content"]) for marker in foreign_markers):
            raise RuntimeError(f"SSE content crossed between conversations: {result['marker']}")
    durations = [float(result["duration_ms"]) for result in results]
    isolated = (
        len(conversation_ids) == concurrency
        and len(message_ids) == concurrency
        and all(message_ids)
    )
    return {
        "concurrency": concurrency,
        "tenants": sorted({str(result["tenant"]) for result in results}),
        "completed": len(results),
        "unique_conversations": len(conversation_ids),
        "unique_messages": len(message_ids),
        "p95_ms": percentile(durations, 0.95),
        "max_ms": round(max(durations), 3),
        "crossed_streams": 0 if isolated else 1,
        "passed": isolated and len(results) == concurrency,
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    base_id = await prepare_performance_corpus(args.chunks)
    retrieval = await benchmark_retrieval(base_id, args.retrieval_requests)
    targets, admin_token = await load_targets()
    timeout = httpx.Timeout(args.timeout, connect=5)
    limits = httpx.Limits(max_connections=max(30, args.sse_concurrency + 5))
    async with httpx.AsyncClient(
        base_url=args.api_base_url.rstrip("/"), timeout=timeout, limits=limits
    ) as client:
        ready = await client.get("/health/ready")
        ready.raise_for_status()
        api = await benchmark_api(client, admin_token, args.api_requests)
        sse = await benchmark_sse(client, targets, args.sse_concurrency)
    passed = retrieval["passed"] and api["passed"] and sse["passed"]
    return {
        "kind": "development_performance_baseline",
        "recorded_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "api_base_url": args.api_base_url,
            "chunk_count": args.chunks,
        },
        "retrieval": retrieval,
        "ordinary_api": api,
        "concurrent_sse": sse,
        "passed": passed,
        "note": (
            "This is a repeatable development baseline. It becomes version acceptance evidence "
            "only when rerun after V1.0 development is frozen in the recorded acceptance "
            "environment."
        ),
    }


async def run_with_cleanup(args: argparse.Namespace) -> dict[str, Any]:
    try:
        return await run(args)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the repeatable V1 performance baseline.")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--chunks", type=int, default=10_000)
    parser.add_argument("--retrieval-requests", type=int, default=100)
    parser.add_argument("--api-requests", type=int, default=100)
    parser.add_argument("--sse-concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()
    if min(args.chunks, args.retrieval_requests, args.api_requests, args.sse_concurrency) <= 0:
        parser.error("chunk and request counts must be positive")
    report = asyncio.run(run_with_cleanup(args))
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if args.enforce and not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
