import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.errors import AppError


async def validate_external_http_url(url: str) -> str:
    parsed = urlsplit(url.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        _raise_unsafe_url()
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        _raise_unsafe_url()
    if get_settings().allow_private_provider_urls:
        return url.rstrip("/")

    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise AppError(
            status_code=400,
            code="provider_host_unresolvable",
            title="Provider host is unavailable",
            detail="The provider host could not be resolved.",
        ) from exc

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            _raise_unsafe_url()
    return url.rstrip("/")


def _raise_unsafe_url() -> None:
    raise AppError(
        status_code=400,
        code="unsafe_provider_url",
        title="Unsafe provider URL",
        detail="The provider URL must resolve only to public HTTP or HTTPS addresses.",
    )
