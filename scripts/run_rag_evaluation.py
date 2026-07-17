import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import select

from app.core.database import async_session_factory, engine
from app.core.security import CustomerPrincipal
from app.domains.applications.models import Application
from app.domains.conversations.schemas import ConversationLocale
from app.domains.conversations.service import (
    CONFLICT_RESPONSE,
    HUMAN_REQUIRED_RESPONSE,
    LOCALIZED_REFUSALS,
    NO_EVIDENCE_RESPONSE,
    SECURITY_REFUSAL_RESPONSE,
    ConversationService,
)
from app.domains.knowledge.service import KnowledgeBaseService
from app.domains.tenants.models import Tenant


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def source_id(source_url: str | None) -> str | None:
    if not source_url:
        return None
    return urlsplit(source_url).path.strip("/") or None


def locale_for_question(question: str) -> ConversationLocale:
    if any("\u3400" <= character <= "\u9fff" for character in question):
        return ConversationLocale.ZH_CN
    return ConversationLocale.EN


def parse_sse(payload: str) -> tuple[str, list[str]]:
    answer = ""
    citations: list[str] = []
    for block in payload.split("\n\n"):
        lines = block.splitlines()
        event = next((line[7:] for line in lines if line.startswith("event: ")), "")
        data = next((line[6:] for line in lines if line.startswith("data: ")), "")
        if event != "message.completed" or not data:
            continue
        message = json.loads(data)
        answer = str(message.get("content", ""))
        citations = [
            value
            for item in message.get("citations", [])
            if (value := source_id(item.get("source_url"))) is not None
        ]
    return answer, list(dict.fromkeys(citations))


async def run_case(session: Any, case: dict[str, Any]) -> dict[str, Any]:
    tenant = await session.scalar(select(Tenant).where(Tenant.slug == case["tenant_id"]))
    if tenant is None:
        raise RuntimeError(f"Tenant is not seeded: {case['tenant_id']}")
    application = await session.scalar(
        select(Application).where(
            Application.tenant_id == tenant.id,
            Application.name == case["application_id"],
        )
    )
    if application is None:
        raise RuntimeError(f"Application is not seeded: {case['application_id']}")

    retrieved = await KnowledgeBaseService(session).search_for_application(
        tenant_id=tenant.id,
        application_id=application.id,
        query=str(case["question"]),
        top_k=20,
    )
    retrieved_sources: list[str] = []
    source_tenants: dict[str, str] = {}
    for result in retrieved:
        value = source_id(result.document.source_url)
        if value is None:
            continue
        if value not in source_tenants:
            retrieved_sources.append(value)
        source_tenants[value] = (
            str(case["tenant_id"])
            if result.document.tenant_id == tenant.id
            else str(result.document.tenant_id)
        )
    principal = CustomerPrincipal(
        tenant_id=tenant.id,
        application_id=application.id,
        external_user_id=f"evaluation:{case['id']}",
        scopes=("chat:read", "chat:write", "handoff:create"),
        token_id=uuid4(),
    )
    service = ConversationService(session)
    conversation = await service.create_session(principal)
    locale = locale_for_question(str(case["question"]))
    prepared = await service.prepare_chat(
        principal=principal,
        conversation_id=conversation.id,
        content=str(case["question"]),
        locale=locale,
        idempotency_key=f"evaluation:{case['id']}",
    )
    stream = "".join([event async for event in service.stream_chat(prepared)])
    answer, cited_sources = parse_sse(stream)
    refusal_responses = {
        NO_EVIDENCE_RESPONSE,
        SECURITY_REFUSAL_RESPONSE,
        CONFLICT_RESPONSE,
        HUMAN_REQUIRED_RESPONSE,
        *(response for responses in LOCALIZED_REFUSALS.values() for response in responses.values()),
    }
    return {
        "case_id": case["id"],
        "answer": answer,
        "retrieved_sources": retrieved_sources,
        "cited_sources": cited_sources,
        "source_tenants": source_tenants,
        "refused": answer in refusal_responses,
        "handoff": answer == LOCALIZED_REFUSALS[locale]["human_required"],
    }


async def run(dataset: Path, output: Path) -> None:
    cases = load_cases(dataset)
    output.parent.mkdir(parents=True, exist_ok=True)
    predictions: list[dict[str, Any]] = []
    async with async_session_factory() as session:
        for index, case in enumerate(cases, start=1):
            predictions.append(await run_case(session, case))
            print(f"[{index}/{len(cases)}] {case['id']}")
    await asyncio.to_thread(
        output.write_text,
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in predictions),
        encoding="utf-8",
    )
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fixed V1 dataset through the platform.")
    parser.add_argument("--dataset", type=Path, default=Path("eval/rag_v1.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.dataset, args.output))


if __name__ == "__main__":
    main()
