import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from app.core.errors import AppError
from app.core.network import validate_external_http_url
from app.providers.llm.base import ChatChunk, ChatMessage


class OpenAICompatibleProvider:
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def test_connection(self) -> None:
        await validate_external_http_url(self.base_url)
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers,
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppError(
                status_code=400,
                code="provider_connection_failed",
                title="Provider connection failed",
                detail="The provider endpoint could not be verified.",
            ) from exc

    async def stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[ChatChunk]:
        await validate_external_http_url(self.base_url)
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
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, follow_redirects=False
            ) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers,
                    json=payload,
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
        await validate_external_http_url(self.base_url)
        payload: dict[str, Any] = {"model": model, "input": list(texts)}
        if dimensions > 0:
            payload["dimensions"] = dimensions
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, follow_redirects=False
            ) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers=self._headers,
                    json=payload,
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
