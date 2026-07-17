import socket
from types import SimpleNamespace

import httpx
import pytest

from app.core.errors import AppError
from app.core.network import validate_external_http_url
from app.providers.llm.openai_compatible import OpenAICompatibleProvider


@pytest.fixture(autouse=True)
def disable_private_provider_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.network.get_settings",
        lambda: SimpleNamespace(allow_private_provider_urls=False),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://provider.example.com/v1",
        "https://user:password@provider.example.com/v1",
        "https://provider.example.com/v1?target=internal",
        "https://provider.example.com/v1#internal",
    ],
)
async def test_provider_url_rejects_unsafe_url_shapes(url: str) -> None:
    with pytest.raises(AppError) as exc_info:
        await validate_external_http_url(url)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "unsafe_provider_url"


@pytest.mark.asyncio
@pytest.mark.parametrize("private_address", ["127.0.0.1", "10.0.0.8", "169.254.169.254", "::1"])
async def test_provider_url_rejects_private_and_metadata_addresses(
    monkeypatch: pytest.MonkeyPatch, private_address: str
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (private_address, 443))
        ],
    )

    with pytest.raises(AppError) as exc_info:
        await validate_external_http_url("https://provider.example.com/v1/")

    assert exc_info.value.code == "unsafe_provider_url"


@pytest.mark.asyncio
async def test_provider_url_rejects_mixed_public_private_dns_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443)),
        ],
    )

    with pytest.raises(AppError) as exc_info:
        await validate_external_http_url("https://provider.example.com/v1")

    assert exc_info.value.code == "unsafe_provider_url"


@pytest.mark.asyncio
async def test_provider_url_accepts_only_public_dns_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
        ],
    )

    normalized = await validate_external_http_url("https://provider.example.com/v1/")

    assert normalized == "https://provider.example.com/v1"


@pytest.mark.asyncio
async def test_provider_url_reports_unresolvable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_dns_error(*_args: object, **_kwargs: object) -> None:
        raise socket.gaierror

    monkeypatch.setattr(socket, "getaddrinfo", raise_dns_error)

    with pytest.raises(AppError) as exc_info:
        await validate_external_http_url("https://missing-provider.example.com/v1")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "provider_host_unresolvable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream_status", "expected_code"),
    [
        (401, "provider_authentication_failed"),
        (403, "provider_authentication_failed"),
        (404, "provider_models_endpoint_not_found"),
        (429, "provider_rate_limited"),
        (503, "provider_unavailable"),
    ],
)
async def test_provider_connection_reports_actionable_upstream_errors(
    monkeypatch: pytest.MonkeyPatch,
    upstream_status: int,
    expected_code: str,
) -> None:
    async def accept_provider_url(url: str) -> str:
        return url

    monkeypatch.setattr(
        "app.providers.llm.openai_compatible.validate_external_http_url",
        accept_provider_url,
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(upstream_status, request=request)
    )
    provider = OpenAICompatibleProvider(
        base_url="https://provider.example.com/v1",
        api_key="secret-key",
        transport=transport,
    )

    with pytest.raises(AppError) as exc_info:
        await provider.test_connection()

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == expected_code
    assert "secret-key" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_provider_connection_accepts_models_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def accept_provider_url(url: str) -> str:
        return url

    monkeypatch.setattr(
        "app.providers.llm.openai_compatible.validate_external_http_url",
        accept_provider_url,
    )
    requested_paths: list[str] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200, request=request, json={"data": []})

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example.com/v1/",
        api_key="secret-key",
        transport=httpx.MockTransport(handle_request),
    )

    await provider.test_connection()

    assert requested_paths == ["/v1/models"]


@pytest.mark.asyncio
async def test_provider_connection_rejects_non_ascii_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def accept_provider_url(url: str) -> str:
        return url

    monkeypatch.setattr(
        "app.providers.llm.openai_compatible.validate_external_http_url",
        accept_provider_url,
    )
    provider = OpenAICompatibleProvider(
        base_url="https://provider.example.com/v1",
        api_key="请填写你的 API Key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, json={"data": []})
        ),
    )

    with pytest.raises(AppError) as exc_info:
        await provider.test_connection()

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "provider_api_key_invalid_format"
