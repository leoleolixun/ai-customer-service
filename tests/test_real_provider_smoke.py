from collections.abc import AsyncIterator, Sequence

import pytest

from app.providers.llm.base import ChatChunk, ChatMessage
from scripts.real_provider_smoke import SmokeOptions, percentile, run_chat_sample, run_smoke


class SuccessfulProvider:
    async def test_connection(self) -> None:
        return None

    async def stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[ChatChunk]:
        del messages, model, temperature, max_tokens
        yield ChatChunk(text="acceptance-")
        yield ChatChunk(
            text="ok",
            prompt_tokens=8,
            completion_tokens=2,
            finish_reason="stop",
        )

    async def embed(
        self,
        *,
        texts: Sequence[str],
        model: str,
        dimensions: int,
    ) -> list[list[float]]:
        del texts, model
        return [[0.25] * dimensions]


class EmptyStreamProvider(SuccessfulProvider):
    async def stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[ChatChunk]:
        del messages, model, temperature, max_tokens
        yield ChatChunk(finish_reason="stop")


def test_percentile_uses_nearest_rank() -> None:
    assert percentile([1, 2, 3, 4, 5], 0.95) == 5


@pytest.mark.asyncio
async def test_real_provider_report_covers_chat_and_embedding_without_content() -> None:
    report = await run_smoke(
        SuccessfulProvider(),
        SmokeOptions(
            base_url="https://provider.example.com/v1",
            chat_model="chat-model",
            samples=3,
            timeout=30,
            first_token_target_ms=5000,
            embedding_model="embedding-model",
            embedding_dimensions=4,
        ),
    )

    assert report["passed"] is True
    assert report["chat"]["samples"] == 3
    assert report["chat"]["temperature"] == 0.2
    assert report["chat"]["max_tokens"] == 256
    assert report["chat"]["runs"][0]["response_characters"] == 13
    assert "response" not in report["chat"]["runs"][0]
    assert report["embedding"]["returned_dimensions"] == 4
    assert report["embedding"]["passed"] is True


@pytest.mark.asyncio
async def test_real_provider_smoke_rejects_a_stream_without_text() -> None:
    with pytest.raises(RuntimeError, match="without a text token"):
        await run_chat_sample(EmptyStreamProvider(), model="chat-model")
