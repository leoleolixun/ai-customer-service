import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import NoReturn
from urllib.parse import urlsplit, urlunsplit

from app.core.config import get_settings
from app.core.errors import AppError


@dataclass(frozen=True, slots=True)
class PinnedHTTPURL:
    normalized_url: str
    connect_url: str
    host_header: str
    sni_hostname: str | None

    @property
    def extensions(self) -> dict[str, str]:
        return {"sni_hostname": self.sni_hostname} if self.sni_hostname else {}


async def resolve_external_http_url(url: str) -> PinnedHTTPURL:
    normalized = url.rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        _raise_unsafe_url()
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        _raise_unsafe_url()
    raw_hostname = parsed.hostname
    if raw_hostname is None:
        _raise_unsafe_url()
    try:
        port = parsed.port
        hostname = raw_hostname.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        _raise_unsafe_url()
    default_port = 443 if parsed.scheme == "https" else 80
    host_literal = f"[{hostname}]" if ":" in hostname else hostname
    host_header = f"{host_literal}:{port}" if port and port != default_port else host_literal
    if get_settings().allow_private_provider_urls:
        return PinnedHTTPURL(
            normalized_url=normalized,
            connect_url=normalized,
            host_header=host_header,
            sni_hostname=hostname if parsed.scheme == "https" else None,
        )

    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port or default_port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise AppError(
            status_code=400,
            code="provider_host_unresolvable",
            title="Provider host is unavailable",
            detail="The provider host could not be resolved.",
        ) from exc

    public_addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for address in addresses:
        ip = ipaddress.ip_address(str(address[4][0]).split("%", maxsplit=1)[0])
        if not ip.is_global:
            _raise_unsafe_url()
        public_addresses.add(ip)
    if not public_addresses:
        _raise_unsafe_url()
    selected = sorted(public_addresses, key=lambda item: (item.version, int(item)))[0]
    selected_host = f"[{selected}]" if selected.version == 6 else str(selected)
    connect_netloc = f"{selected_host}:{port}" if port else selected_host
    connect_url = urlunsplit((parsed.scheme, connect_netloc, parsed.path, "", ""))
    return PinnedHTTPURL(
        normalized_url=normalized,
        connect_url=connect_url,
        host_header=host_header,
        sni_hostname=hostname if parsed.scheme == "https" else None,
    )


async def validate_external_http_url(url: str) -> str:
    return (await resolve_external_http_url(url)).normalized_url


def _raise_unsafe_url() -> NoReturn:
    raise AppError(
        status_code=400,
        code="unsafe_provider_url",
        title="Unsafe provider URL",
        detail="The provider URL must resolve only to public HTTP or HTTPS addresses.",
    )
