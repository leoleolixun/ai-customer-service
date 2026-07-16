from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.core.database import async_session_factory, engine
from app.core.security import StaffPrincipal
from app.core.storage import get_object_storage
from app.domains.identities.models import StaffUser, TenantMembership, TenantRole
from app.domains.knowledge.models import (
    DocumentStatus,
    IngestionJob,
    IngestionStatus,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.domains.knowledge.service import DocumentService
from app.domains.tenants.models import Tenant
from app.workers.knowledge import ingest_knowledge_document


async def enqueue_probe(state_path: Path) -> dict[str, Any]:
    marker = f"worker-recovery-{uuid4().hex}"
    content = (
        "# Worker recovery probe\n\n"
        f"Document {marker} must remain queued while the worker is offline and be processed "
        "exactly once after it restarts."
    ).encode()
    async with async_session_factory() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == "demo-retail"))
        if tenant is None:
            raise RuntimeError("Run scripts/seed_demo.py before the worker recovery probe.")
        knowledge_base = await session.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.tenant_id == tenant.id,
                KnowledgeBase.name == "V1 evaluation corpus",
            )
        )
        if knowledge_base is None:
            raise RuntimeError("The demo-retail evaluation knowledge base is missing.")
        staff_row = (
            await session.execute(
                select(StaffUser, TenantMembership)
                .join(
                    TenantMembership,
                    TenantMembership.staff_user_id == StaffUser.id,
                )
                .where(
                    TenantMembership.tenant_id == tenant.id,
                    TenantMembership.role == TenantRole.TENANT_ADMIN,
                )
            )
        ).first()
        if staff_row is None:
            raise RuntimeError("The demo-retail tenant administrator is missing.")
        staff, membership = staff_row
        actor = StaffPrincipal(
            user_id=staff.id,
            email=staff.email,
            is_platform_admin=staff.is_platform_admin,
            tenant_id=tenant.id,
            role=membership.role,
        )
        document, job = await DocumentService(session, get_object_storage()).upload(
            tenant_id=tenant.id,
            base_id=knowledge_base.id,
            title="Worker recovery probe",
            filename=f"{marker}.md",
            mime_type="text/markdown",
            content=content,
            source_url=f"https://demo-retail.example.com/probes/{marker}",
            replace_document_id=None,
            actor=actor,
            request_id=marker,
        )
    task = ingest_knowledge_document.delay(str(tenant.id), str(document.id))
    state = {
        "tenant_id": str(tenant.id),
        "knowledge_base_id": str(knowledge_base.id),
        "document_id": str(document.id),
        "job_id": str(job.id),
        "task_id": str(task.id),
        "marker": marker,
    }
    await asyncio.to_thread(state_path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(
        state_path.write_text,
        json.dumps(state, indent=2) + "\n",
        encoding="utf-8",
    )
    return state


async def ingestion_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    tenant_id = UUID(str(state["tenant_id"]))
    document_id = UUID(str(state["document_id"]))
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(KnowledgeDocument, IngestionJob)
                .join(IngestionJob, IngestionJob.document_id == KnowledgeDocument.id)
                .where(
                    KnowledgeDocument.tenant_id == tenant_id,
                    KnowledgeDocument.id == document_id,
                    IngestionJob.tenant_id == tenant_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError("The recovery probe document or job no longer exists.")
        document, job = row
        chunk_count = int(
            await session.scalar(
                select(func.count(KnowledgeChunk.id)).where(
                    KnowledgeChunk.tenant_id == tenant_id,
                    KnowledgeChunk.document_id == document_id,
                )
            )
            or 0
        )
        return {
            "document_status": document.status.value,
            "job_status": job.status.value,
            "stage": job.stage,
            "attempts": job.attempts,
            "chunk_count": chunk_count,
            "error": job.error_message,
        }


async def wait_until_completed(state: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        snapshot = await ingestion_snapshot(state)
        if (
            snapshot["document_status"] == DocumentStatus.READY.value
            and snapshot["job_status"] == IngestionStatus.COMPLETED.value
            and snapshot["stage"] == "published"
        ):
            if int(snapshot["chunk_count"]) <= 0:
                raise RuntimeError("The completed recovery probe has no chunks.")
            return snapshot
        if snapshot["job_status"] == IngestionStatus.FAILED.value:
            raise RuntimeError(f"The recovery probe failed: {snapshot['error']}")
        await asyncio.sleep(0.5)
    raise TimeoutError(f"The recovery probe did not complete within {timeout_seconds:.0f} seconds.")


async def verify_probe(state_path: Path, timeout_seconds: float, replay: bool) -> dict[str, Any]:
    state_text = await asyncio.to_thread(state_path.read_text, encoding="utf-8")
    state = json.loads(state_text)
    first = await wait_until_completed(state, timeout_seconds)
    result: dict[str, Any] = {"first_completion": first}
    if replay:
        replay_result = ingest_knowledge_document.delay(
            str(state["tenant_id"]), str(state["document_id"])
        )
        await asyncio.to_thread(replay_result.get, timeout=timeout_seconds, propagate=True)
        second = await ingestion_snapshot(state)
        idempotent = (
            second["attempts"] == first["attempts"]
            and second["chunk_count"] == first["chunk_count"]
            and second["stage"] == "published"
        )
        result.update(
            {
                "replay_task_id": str(replay_result.id),
                "second_completion": second,
                "idempotent_replay": idempotent,
            }
        )
        if not idempotent:
            raise RuntimeError("Replaying the completed ingestion task changed persisted state.")
    result["passed"] = True
    return result


async def run_command(args: argparse.Namespace) -> dict[str, Any]:
    try:
        if args.command == "enqueue":
            return await enqueue_probe(args.state)
        return await verify_probe(args.state, args.timeout, args.replay)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify queued Worker recovery and idempotency.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    enqueue_parser = subparsers.add_parser("enqueue")
    enqueue_parser.add_argument("--state", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument("--timeout", type=float, default=60.0)
    verify_parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    try:
        result = asyncio.run(run_command(args))
    except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
