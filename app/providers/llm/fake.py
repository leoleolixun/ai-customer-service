import hashlib
import math
import re
from collections.abc import AsyncIterator, Sequence

from app.providers.llm.base import ChatChunk, ChatMessage


class FakeChatProvider:
    async def stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[ChatChunk]:
        del model, temperature, max_tokens
        user_message = next(
            (message.content for message in reversed(messages) if message.role == "user"), ""
        )
        response = f"Fake assistant: {user_message}"
        system_message = next(
            (message.content for message in messages if message.role == "system"), ""
        )
        if "\nEVIDENCE:" in system_message:
            evidence = system_message.split("\nEVIDENCE:", maxsplit=1)[1].strip()
            response = f"{response}\n\nVerified information:\n{evidence}"
        prompt_tokens = sum(max(1, len(message.content) // 4) for message in messages)
        completion_tokens = max(1, len(response) // 4)
        for word in response.split(" "):
            yield ChatChunk(text=f"{word} ")
        yield ChatChunk(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason="stop",
        )


class FakeEmbeddingProvider:
    async def embed(
        self,
        *,
        texts: Sequence[str],
        model: str,
        dimensions: int,
    ) -> list[list[float]]:
        del model
        return [self._vector(text, dimensions) for text in texts]

    @staticmethod
    def _vector(text: str, dimensions: int) -> list[float]:
        values = [0.0] * dimensions
        for token in FakeEmbeddingProvider._tokens(text):
            digest = hashlib.sha256(token.encode()).digest()
            position = int.from_bytes(digest[:4], "big") % dimensions
            values[position] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    @staticmethod
    def _tokens(text: str) -> list[str]:
        normalized = text.casefold()
        words = re.findall(r"[a-z0-9]+", normalized)
        cjk = re.findall(r"[\u3400-\u9fff]", normalized)
        cjk_bigrams = ["".join(cjk[index : index + 2]) for index in range(len(cjk) - 1)]
        return [*words, *cjk, *cjk_bigrams] or [normalized]
