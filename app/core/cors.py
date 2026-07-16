from collections.abc import Iterable

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_ALLOWED_METHOD_SET = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
_ALLOWED_METHODS = ", ".join(sorted(_ALLOWED_METHOD_SET))
_ALLOWED_HEADERS = frozenset(
    {
        "authorization",
        "content-type",
        "idempotency-key",
        "x-api-key",
        "x-request-id",
    }
)
_PUBLIC_CROSS_ORIGIN_PREFIXES = ("/v1/chat/", "/sdk/", "/widget/")


class PathAwareCORSMiddleware:
    """Allow dynamic Widget origins while keeping staff APIs on a deployment allowlist."""

    def __init__(self, app: ASGIApp, *, staff_origins: Iterable[str]) -> None:
        self.app = app
        self.staff_origins = frozenset(staff_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)
        origin = request_headers.get("origin")
        if origin is None:
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        origin_allowed = path.startswith(_PUBLIC_CROSS_ORIGIN_PREFIXES) or (
            origin in self.staff_origins
        )
        is_preflight = (
            scope["method"] == "OPTIONS"
            and request_headers.get("access-control-request-method") is not None
        )
        if is_preflight:
            await self._preflight(request_headers, origin, origin_allowed, scope, receive, send)
            return

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start" and origin_allowed:
                headers = MutableHeaders(scope=message)
                headers["Access-Control-Allow-Origin"] = origin
                headers.add_vary_header("Origin")
                headers["Access-Control-Expose-Headers"] = "X-Request-ID"
            await send(message)

        await self.app(scope, receive, send_with_cors)

    async def _preflight(
        self,
        request_headers: Headers,
        origin: str,
        origin_allowed: bool,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        requested_method = request_headers.get("access-control-request-method", "").upper()
        requested_headers = {
            value.strip().lower()
            for value in request_headers.get("access-control-request-headers", "").split(",")
            if value.strip()
        }
        if (
            not origin_allowed
            or requested_method not in _ALLOWED_METHOD_SET
            or not requested_headers <= _ALLOWED_HEADERS
        ):
            await PlainTextResponse("Disallowed CORS request", status_code=400)(
                scope, receive, send
            )
            return

        response = Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": _ALLOWED_METHODS,
                "Access-Control-Allow-Headers": ", ".join(sorted(_ALLOWED_HEADERS)),
                "Access-Control-Max-Age": "600",
                "Vary": "Origin",
            },
        )
        await response(scope, receive, send)
