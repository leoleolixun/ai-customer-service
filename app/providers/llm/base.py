from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ChatChunk:
    text: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str | None = None


class ChatProvider(Protocol):
    def stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[ChatChunk]: ...


class EmbeddingProvider(Protocol):
    async def embed(
        self,
        *,
        texts: Sequence[str],
        model: str,
        dimensions: int,
    ) -> list[list[float]]: ...
