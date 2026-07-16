from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.test_chat_api import issue_customer_token, setup_chat_application


async def test_customer_chat_uses_application_origins_without_global_restart(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await setup_chat_application(client, session_factory)
    token = await issue_customer_token(client, setup["api_key"], "cors-user")
    authorization = {"Authorization": f"Bearer {token}"}

    preflight = await client.options(
        "/v1/chat/sessions",
        headers={
            "Origin": "https://chat.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )
    assert preflight.status_code == 204
    assert preflight.headers["access-control-allow-origin"] == "https://chat.example.com"

    rejected = await client.post(
        "/v1/chat/sessions",
        headers={**authorization, "Origin": "https://evil.example.com"},
        json={},
    )
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "origin_not_allowed"

    accepted = await client.post(
        "/v1/chat/sessions",
        headers={**authorization, "Origin": "https://chat.example.com"},
        json={},
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.headers["access-control-allow-origin"] == "https://chat.example.com"


async def test_staff_cors_remains_on_the_deployment_allowlist(client: AsyncClient) -> None:
    rejected = await client.options(
        "/v1/admin/me",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers

    accepted = await client.options(
        "/v1/admin/me",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert accepted.status_code == 204
    assert accepted.headers["access-control-allow-origin"] == "http://localhost:5173"
