import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from app.core.errors import AppError
from app.core.network import PinnedHTTPURL, resolve_external_http_url
from app.providers.llm.base import ChatChunk, ChatMessage, ChatThinkingMode


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def test_connection(self) -> None:
        target = await resolve_external_http_url(self.base_url)
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=False,
                transport=self.transport,
                trust_env=False,
            ) as client:
                response = await client.request(
                    "GET",
                    f"{target.connect_url}/models",
                    headers=self._request_headers(target),
                    extensions=target.extensions,
                )
        except UnicodeEncodeError as exc:
            raise AppError(
                status_code=400,
                code="provider_api_key_invalid_format",
                title="Provider API key format is invalid",
                detail=(
                    "The API key must contain ASCII characters only. "
                    "Do not include labels, quotes, or the Bearer prefix."
                ),
            ) from exc
        except httpx.TimeoutException as exc:
            raise AppError(
                status_code=400,
                code="provider_connection_timeout",
                title="Provider connection timed out",
                detail="The provider did not respond within 10 seconds.",
            ) from exc
        except httpx.RequestError as exc:
            raise AppError(
                status_code=400,
                code="provider_connection_unreachable",
                title="Provider connection failed",
                detail="Could not connect to the provider. Check its Base URL, DNS, and TLS.",
            ) from exc

        if 200 <= response.status_code < 300:
            return
        if response.status_code in {401, 403}:
            raise AppError(
                status_code=400,
                code="provider_authentication_failed",
                title="Provider authentication failed",
                detail="The provider rejected the API key. Enter a valid, unexpired key.",
            )
        if response.status_code == 404:
            raise AppError(
                status_code=400,
                code="provider_models_endpoint_not_found",
                title="Provider models endpoint not found",
                detail=(
                    "The provider does not expose GET /models at this Base URL. "
                    "Enter the API root, not a /chat/completions endpoint."
                ),
            )
        if response.status_code == 429:
            raise AppError(
                status_code=400,
                code="provider_rate_limited",
                title="Provider rate limit reached",
                detail="The provider rate-limited the connection test. Try again later.",
            )
        if response.status_code >= 500:
            raise AppError(
                status_code=400,
                code="provider_unavailable",
                title="Provider unavailable",
                detail="The provider is temporarily unavailable. Try again later.",
            )
        raise AppError(
            status_code=400,
            code="provider_connection_failed",
            title="Provider connection failed",
            detail=f"The provider rejected the connection test with HTTP {response.status_code}.",
        )

    async def stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        thinking_mode: ChatThinkingMode,
    ) -> AsyncIterator[ChatChunk]:
        target = await resolve_external_http_url(self.base_url)
        payload = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if thinking_mode != "provider_default":
            payload["thinking"] = {"type": thinking_mode}
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
                transport=self.transport,
                trust_env=False,
            ) as client:
                async with client.stream(
                    "POST",
                    f"{target.connect_url}/chat/completions",
                    headers=self._request_headers(target),
                    json=payload,
                    extensions=target.extensions,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            break
                        chunk = self._parse_chunk(json.loads(data))
                        if chunk is not None:
                            yield chunk
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise AppError(
                status_code=502,
                code="model_provider_failed",
                title="Model provider failed",
                detail="The model provider request failed.",
            ) from exc

    async def embed(
        self,
        *,
        texts: Sequence[str],
        model: str,
        dimensions: int,
    ) -> list[list[float]]:
        target = await resolve_external_http_url(self.base_url)
        payload: dict[str, Any] = {"model": model, "input": list(texts)}
        if dimensions > 0:
            payload["dimensions"] = dimensions
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
                transport=self.transport,
                trust_env=False,
            ) as client:
                response = await client.request(
                    "POST",
                    f"{target.connect_url}/embeddings",
                    headers=self._request_headers(target),
                    json=payload,
                    extensions=target.extensions,
                )
                response.raise_for_status()
            body = response.json()
            ordered = sorted(body["data"], key=lambda item: item["index"])
            return [[float(value) for value in item["embedding"]] for item in ordered]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise AppError(
                status_code=502,
                code="embedding_provider_failed",
                title="Embedding provider failed",
                detail="The embedding provider request failed.",
            ) from exc

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _request_headers(self, target: PinnedHTTPURL) -> dict[str, str]:
        return {**self._headers, "Host": target.host_header}

    @staticmethod
    def _parse_chunk(data: dict[str, Any]) -> ChatChunk | None:
        usage = data.get("usage") or {}
        choices = data.get("choices") or []
        text = ""
        finish_reason = None
        if choices:
            text = str((choices[0].get("delta") or {}).get("content") or "")
            finish_reason = choices[0].get("finish_reason")
        if text or finish_reason or usage:
            return ChatChunk(
                text=text,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                finish_reason=finish_reason,
            )
        return None
