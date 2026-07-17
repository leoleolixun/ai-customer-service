import json
import socket
from types import SimpleNamespace

import httpx
import pytest

from app.core.errors import AppError
from app.core.network import PinnedHTTPURL, resolve_external_http_url, validate_external_http_url
from app.providers.llm.base import ChatMessage, ChatThinkingMode
from app.providers.llm.openai_compatible import OpenAICompatibleProvider


@pytest.fixture(autouse=True)
def disable_private_provider_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.network.get_settings",
        lambda: SimpleNamespace(allow_private_provider_urls=False),
    )


async def accept_provider_url(url: str) -> PinnedHTTPURL:
    normalized = url.rstrip("/")
    return PinnedHTTPURL(
        normalized_url=normalized,
        connect_url=normalized,
        host_header="provider.example.com",
        sni_hostname="provider.example.com",
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
async def test_provider_url_pins_the_validated_ip_for_the_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
        ],
    )

    target = await resolve_external_http_url("https://provider.example.com/v1")

    assert target.connect_url == "https://93.184.216.34/v1"
    assert target.host_header == "provider.example.com"
    assert target.extensions == {"sni_hostname": "provider.example.com"}


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
    monkeypatch.setattr(
        "app.providers.llm.openai_compatible.resolve_external_http_url",
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
    monkeypatch.setattr(
        "app.providers.llm.openai_compatible.resolve_external_http_url",
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
    monkeypatch.setattr(
        "app.providers.llm.openai_compatible.resolve_external_http_url",
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


@pytest.mark.asyncio
async def test_provider_request_uses_pinned_ip_with_original_host_and_sni(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
        ],
    )
    captured: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, request=request, json={"data": []})

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example.com/v1",
        api_key="secret-key",
        transport=httpx.MockTransport(handle_request),
    )

    await provider.test_connection()

    assert str(captured[0].url) == "https://93.184.216.34/v1/models"
    assert captured[0].headers["host"] == "provider.example.com"
    assert captured[0].extensions["sni_hostname"] == "provider.example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("thinking_mode", "expected_thinking"),
    [
        ("provider_default", None),
        ("disabled", {"type": "disabled"}),
        ("enabled", {"type": "enabled"}),
    ],
)
async def test_provider_stream_sends_configured_thinking_mode(
    monkeypatch: pytest.MonkeyPatch,
    thinking_mode: ChatThinkingMode,
    expected_thinking: dict[str, str] | None,
) -> None:
    monkeypatch.setattr(
        "app.providers.llm.openai_compatible.resolve_external_http_url",
        accept_provider_url,
    )
    payloads: list[dict[str, object]] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        stream = (
            'data: {"choices":[{"delta":{"content":"answer"},'
            '"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
            '"usage":{"prompt_tokens":3,"completion_tokens":1}}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, request=request, text=stream)

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example.com/v1",
        api_key="secret-key",
        transport=httpx.MockTransport(handle_request),
    )
    chunks = [
        chunk
        async for chunk in provider.stream(
            messages=[ChatMessage(role="user", content="question")],
            model="chat-model",
            temperature=0.2,
            max_tokens=256,
            thinking_mode=thinking_mode,
        )
    ]

    assert "".join(chunk.text for chunk in chunks) == "answer"
    assert payloads[0].get("thinking") == expected_thinking
    if expected_thinking is None:
        assert "thinking" not in payloads[0]


@pytest.mark.asyncio
async def test_provider_embedding_contract_sends_request_and_restores_input_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.providers.llm.openai_compatible.resolve_external_http_url",
        accept_provider_url,
    )
    captured: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            request=request,
            json={
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example.com/v1",
        api_key="secret-key",
        transport=httpx.MockTransport(handle_request),
    )

    vectors = await provider.embed(texts=["first", "second"], model="embedding-model", dimensions=2)

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert captured[0].url.path == "/v1/embeddings"
    assert captured[0].headers["authorization"] == "Bearer secret-key"
    assert captured[0].headers["host"] == "provider.example.com"
    assert json.loads(captured[0].content) == {
        "model": "embedding-model",
        "input": ["first", "second"],
        "dimensions": 2,
    }


@pytest.mark.asyncio
async def test_provider_embedding_omits_unspecified_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.providers.llm.openai_compatible.resolve_external_http_url",
        accept_provider_url,
    )
    payloads: list[dict[str, object]] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            request=request,
            json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]},
        )

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example.com/v1",
        api_key="secret-key",
        transport=httpx.MockTransport(handle_request),
    )

    assert await provider.embed(texts=["first"], model="embedding-model", dimensions=0) == [
        [0.1, 0.2]
    ]
    assert payloads == [{"model": "embedding-model", "input": ["first"]}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_data",
    [
        [{"index": 0, "embedding": [0.1, 0.2]}],
        [
            {"index": 0, "embedding": [0.1, 0.2]},
            {"index": 0, "embedding": [0.3, 0.4]},
        ],
        [
            {"index": 0, "embedding": [0.1]},
            {"index": 1, "embedding": [0.3, 0.4]},
        ],
        [
            {"index": 0, "embedding": [0.1, float("nan")]},
            {"index": 1, "embedding": [0.3, 0.4]},
        ],
    ],
)
async def test_provider_embedding_rejects_invalid_response_contract(
    monkeypatch: pytest.MonkeyPatch,
    response_data: list[dict[str, object]],
) -> None:
    monkeypatch.setattr(
        "app.providers.llm.openai_compatible.resolve_external_http_url",
        accept_provider_url,
    )
    provider = OpenAICompatibleProvider(
        base_url="https://provider.example.com/v1",
        api_key="secret-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, json={"data": response_data})
        ),
    )

    with pytest.raises(AppError) as exc_info:
        await provider.embed(texts=["first", "second"], model="embedding-model", dimensions=2)

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "embedding_provider_failed"
