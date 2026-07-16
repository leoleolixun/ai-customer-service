import socket
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.core.network import validate_external_http_url


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
