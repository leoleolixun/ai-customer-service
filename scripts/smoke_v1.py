from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

from app.core.database import async_session_factory, engine
from app.domains.applications.models import Application
from app.domains.tenants.models import Tenant
from scripts.password_input import read_password


@dataclass(frozen=True, slots=True)
class DemoDefinition:
    slug: str
    admin_email: str
    application_name: str
    answerable_question: str
    refusal_question: str


@dataclass(slots=True)
class DemoRun:
    definition: DemoDefinition
    tenant_id: UUID
    application_id: UUID
    conversation_id: UUID
    credential_id: UUID
    citation_id: UUID
    admin_token: str = field(repr=False)
    customer_token: str = field(repr=False)


DEMOS = (
    DemoDefinition(
        slug="demo-retail",
        admin_email="admin@demo-retail.example",
        application_name="storefront-web",
        answerable_question="普通商品签收后多久还能申请退货?",
        refusal_question="下个月会推出什么颜色的新款背包?",
    ),
    DemoDefinition(
        slug="demo-saas",
        admin_email="admin@demo-saas.example",
        application_name="help-center-web",
        answerable_question="新工作区可以免费试用多久?",
        refusal_question="下一个大版本会在哪一天发布?",
    ),
)


def normalize_base_url(value: str) -> str:
    parsed = urlsplit(value.rstrip("/"))
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("base URL must contain only an HTTP(S) scheme and host")
    return value.rstrip("/")


def parse_completed_message(payload: str) -> dict[str, Any]:
    completed: dict[str, Any] | None = None
    for block in payload.split("\n\n"):
        lines = block.splitlines()
        event = next((line[7:] for line in lines if line.startswith("event: ")), "")
        data = next((line[6:] for line in lines if line.startswith("data: ")), "")
        if not data:
            continue
        decoded = json.loads(data)
        if event == "message.error":
            raise RuntimeError(f"chat stream failed: {decoded.get('code', 'unknown_error')}")
        if event == "message.completed" and isinstance(decoded, dict):
            completed = decoded
    if completed is None:
        raise RuntimeError("chat stream did not contain message.completed")
    return completed


async def load_target(definition: DemoDefinition) -> tuple[UUID, UUID]:
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(Tenant.id, Application.id)
                .join(Application, Application.tenant_id == Tenant.id)
                .where(
                    Tenant.slug == definition.slug,
                    Application.name == definition.application_name,
                )
            )
        ).one_or_none()
    if row is None:
        raise RuntimeError(
            f"demo target {definition.slug}/{definition.application_name} is not seeded"
        )
    return row[0], row[1]


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    expected: int = 200,
    **kwargs: Any,
) -> Any:
    response = await client.request(method, path, **kwargs)
    if response.status_code != expected:
        try:
            body = response.json()
            code = body.get("code", "http_error") if isinstance(body, dict) else "http_error"
        except ValueError:
            code = "http_error"
        raise RuntimeError(f"{method} {path} returned {response.status_code} ({code})")
    return response.json() if response.content else None


async def run_demo(
    client: httpx.AsyncClient,
    definition: DemoDefinition,
    password: str,
) -> DemoRun:
    tenant_id, application_id = await load_target(definition)
    login = await request_json(
        client,
        "POST",
        "/v1/admin/auth/login",
        json={
            "email": definition.admin_email,
            "password": password,
            "tenant_id": str(tenant_id),
        },
    )
    admin_token = str(login["access_token"])
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    applications = await request_json(
        client,
        "GET",
        "/v1/admin/applications",
        headers=admin_headers,
    )
    if str(application_id) not in {str(item["id"]) for item in applications}:
        raise RuntimeError(f"{definition.slug} application is missing from the admin API")

    credential = await request_json(
        client,
        "POST",
        f"/v1/admin/applications/{application_id}/credentials",
        expected=201,
        headers=admin_headers,
        json={"scopes": ["customer_token:create"]},
    )
    credential_id = UUID(str(credential["id"]))
    try:
        customer = await request_json(
            client,
            "POST",
            "/v1/customer-tokens",
            headers={"X-API-Key": str(credential["api_key"])},
            json={"external_user_id": f"v1-smoke:{uuid4()}"},
        )
        customer_token = str(customer["access_token"])
        customer_headers = {"Authorization": f"Bearer {customer_token}"}
        conversation = await request_json(
            client,
            "POST",
            "/v1/chat/sessions",
            expected=201,
            headers=customer_headers,
            json={},
        )
        conversation_id = UUID(str(conversation["id"]))

        answer_response = await client.post(
            f"/v1/chat/sessions/{conversation_id}/messages",
            headers={**customer_headers, "Idempotency-Key": f"smoke-answer:{uuid4()}"},
            json={"content": definition.answerable_question},
        )
        if answer_response.status_code != 200:
            raise RuntimeError(
                f"answerable chat returned {answer_response.status_code} for {definition.slug}"
            )
        answer = parse_completed_message(answer_response.text)
        citations = answer.get("citations") or []
        if not answer.get("content") or not citations:
            raise RuntimeError(f"{definition.slug} answer did not contain content and citations")
        citation_id = UUID(str(citations[0]["id"]))
        source = await client.get(
            f"/v1/chat/sessions/{conversation_id}/citations/{citation_id}/source",
            headers=customer_headers,
        )
        if source.status_code != 200 or not source.content:
            raise RuntimeError(f"{definition.slug} citation source could not be opened")

        refusal_response = await client.post(
            f"/v1/chat/sessions/{conversation_id}/messages",
            headers={**customer_headers, "Idempotency-Key": f"smoke-refusal:{uuid4()}"},
            json={"content": definition.refusal_question},
        )
        if refusal_response.status_code != 200:
            raise RuntimeError(
                f"refusal chat returned {refusal_response.status_code} for {definition.slug}"
            )
        refusal = parse_completed_message(refusal_response.text)
        if not refusal.get("content") or refusal.get("citations"):
            raise RuntimeError(
                f"{definition.slug} no-answer case was not refused without citations"
            )

        handoff = await request_json(
            client,
            "POST",
            f"/v1/chat/sessions/{conversation_id}/handoff",
            expected=201,
            headers=customer_headers,
            json={"reason": "V1 smoke test human handoff"},
        )
        handoff_id = UUID(str(handoff["id"]))
        await request_json(
            client,
            "POST",
            f"/v1/admin/handoffs/{handoff_id}/accept",
            headers=admin_headers,
        )
        await request_json(
            client,
            "POST",
            f"/v1/admin/handoffs/{handoff_id}/messages",
            expected=201,
            headers=admin_headers,
            json={"content": "A human agent completed the V1 smoke test."},
        )
        await request_json(
            client,
            "POST",
            f"/v1/admin/handoffs/{handoff_id}/close",
            headers=admin_headers,
            json={"reason": "smoke test complete"},
        )
        messages = await request_json(
            client,
            "GET",
            f"/v1/chat/sessions/{conversation_id}/messages",
            headers=customer_headers,
        )
        if not any(item.get("sender") == "agent" for item in messages):
            raise RuntimeError(f"{definition.slug} did not expose the human agent reply")
        return DemoRun(
            definition=definition,
            tenant_id=tenant_id,
            application_id=application_id,
            conversation_id=conversation_id,
            credential_id=credential_id,
            citation_id=citation_id,
            admin_token=admin_token,
            customer_token=customer_token,
        )
    except Exception:
        await revoke_credential(
            client,
            application_id=application_id,
            credential_id=credential_id,
            admin_token=admin_token,
        )
        raise


async def revoke_credential(
    client: httpx.AsyncClient,
    *,
    application_id: UUID,
    credential_id: UUID,
    admin_token: str,
) -> None:
    await request_json(
        client,
        "DELETE",
        f"/v1/admin/applications/{application_id}/credentials/{credential_id}",
        expected=204,
        headers={"Authorization": f"Bearer {admin_token}"},
    )


async def run(base_url: str, password: str) -> None:
    runs: list[DemoRun] = []
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(60, connect=10),
        follow_redirects=False,
    ) as client:
        try:
            for definition in DEMOS:
                runs.append(await run_demo(client, definition, password))
            cross_tenant = await client.get(
                f"/v1/chat/sessions/{runs[1].conversation_id}",
                headers={"Authorization": f"Bearer {runs[0].customer_token}"},
            )
            if cross_tenant.status_code != 404:
                raise RuntimeError(
                    f"cross-tenant conversation access returned {cross_tenant.status_code}"
                )
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "tenants": [run.definition.slug for run in runs],
                        "checks": [
                            "admin_auth",
                            "application_credential",
                            "customer_token",
                            "cited_answer",
                            "citation_source",
                            "no_answer_refusal",
                            "human_handoff",
                            "cross_tenant_isolation",
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            for result in runs:
                await revoke_credential(
                    client,
                    application_id=result.application_id,
                    credential_id=result.credential_id,
                    admin_token=result.admin_token,
                )
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the V1 two-tenant HTTP smoke workflow.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the shared demo administrator password from standard input.",
    )
    args = parser.parse_args()
    try:
        base_url = normalize_base_url(args.base_url)
    except ValueError as exc:
        parser.error(str(exc))
    password = read_password(
        from_stdin=args.password_stdin,
        prompt="Demo administrator password: ",
    )
    if len(password) < 12:
        parser.error("password must contain at least 12 characters")
    asyncio.run(run(base_url, password))


if __name__ == "__main__":
    main()
