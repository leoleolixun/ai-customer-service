from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import sys
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.core.errors import AppError
from app.providers.llm.base import ChatChunk, ChatMessage
from app.providers.llm.openai_compatible import OpenAICompatibleProvider

API_KEY_ENV = "AI_CS_PROVIDER_API_KEY"


class SmokeProvider(Protocol):
    async def test_connection(self) -> None: ...

    def stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[ChatChunk]: ...

    async def embed(
        self,
        *,
        texts: Sequence[str],
        model: str,
        dimensions: int,
    ) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class SmokeOptions:
    base_url: str
    chat_model: str
    samples: int
    timeout: float
    first_token_target_ms: float
    embedding_model: str | None = None
    embedding_dimensions: int = 0


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        raise ValueError("at least one sample is required")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return round(ordered[index], 3)


async def run_chat_sample(
    provider: SmokeProvider,
    *,
    model: str,
) -> dict[str, Any]:
    started = perf_counter()
    first_token_ms: float | None = None
    response_length = 0
    prompt_tokens = 0
    completion_tokens = 0
    finish_reason: str | None = None
    async for chunk in provider.stream(
        messages=[
            ChatMessage(
                role="user",
                content="Reply with exactly acceptance-ok and no additional text.",
            )
        ],
        model=model,
        temperature=0,
        max_tokens=32,
    ):
        if chunk.text:
            if first_token_ms is None:
                first_token_ms = (perf_counter() - started) * 1000
            response_length += len(chunk.text)
        prompt_tokens += chunk.prompt_tokens
        completion_tokens += chunk.completion_tokens
        finish_reason = chunk.finish_reason or finish_reason

    if first_token_ms is None or response_length == 0:
        raise RuntimeError("provider stream completed without a text token")
    return {
        "first_token_ms": round(first_token_ms, 3),
        "completed_ms": round((perf_counter() - started) * 1000, 3),
        "response_characters": response_length,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "finish_reason": finish_reason,
    }


async def run_smoke(provider: SmokeProvider, options: SmokeOptions) -> dict[str, Any]:
    connection_started = perf_counter()
    await provider.test_connection()
    connection_ms = round((perf_counter() - connection_started) * 1000, 3)

    samples = [
        await run_chat_sample(provider, model=options.chat_model) for _ in range(options.samples)
    ]
    first_token_values = [float(sample["first_token_ms"]) for sample in samples]
    completion_values = [float(sample["completed_ms"]) for sample in samples]
    first_token_p95 = percentile(first_token_values, 0.95)
    chat_passed = first_token_p95 < options.first_token_target_ms

    embedding: dict[str, Any] | None = None
    if options.embedding_model:
        embedding_started = perf_counter()
        vectors = await provider.embed(
            texts=["AI customer service acceptance embedding probe."],
            model=options.embedding_model,
            dimensions=options.embedding_dimensions,
        )
        dimension = len(vectors[0]) if len(vectors) == 1 else 0
        values_are_finite = len(vectors) == 1 and all(math.isfinite(value) for value in vectors[0])
        embedding_passed = dimension == options.embedding_dimensions and values_are_finite
        embedding = {
            "model": options.embedding_model,
            "requested_dimensions": options.embedding_dimensions,
            "returned_vectors": len(vectors),
            "returned_dimensions": dimension,
            "values_are_finite": values_are_finite,
            "latency_ms": round((perf_counter() - embedding_started) * 1000, 3),
            "passed": embedding_passed,
        }

    return {
        "kind": "real_openai_compatible_provider_smoke",
        "recorded_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "provider_host": urlsplit(options.base_url).hostname,
            "base_url": options.base_url.rstrip("/"),
            "api_key_source": API_KEY_ENV,
        },
        "connection": {"latency_ms": connection_ms, "passed": True},
        "chat": {
            "model": options.chat_model,
            "samples": options.samples,
            "first_token_p50_ms": percentile(first_token_values, 0.50),
            "first_token_p95_ms": first_token_p95,
            "first_token_target_ms": options.first_token_target_ms,
            "completion_p50_ms": percentile(completion_values, 0.50),
            "completion_p95_ms": percentile(completion_values, 0.95),
            "runs": samples,
            "passed": chat_passed,
        },
        "embedding": embedding,
        "passed": chat_passed and (embedding is None or bool(embedding["passed"])),
    }


def write_report(report: dict[str, Any], output: Path | None) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure a real OpenAI-compatible provider without persisting its API key."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--chat-model", required=True)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--first-token-target-ms", type=float, default=5000.0)
    parser.add_argument("--embedding-model")
    parser.add_argument("--embedding-dimensions", type=int, default=0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--enforce", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.samples <= 0 or args.timeout <= 0 or args.first_token_target_ms <= 0:
        print("samples, timeout, and first-token target must be positive", file=sys.stderr)
        return 2
    if bool(args.embedding_model) != (args.embedding_dimensions > 0):
        print(
            "embedding model and a positive embedding dimension must be provided together",
            file=sys.stderr,
        )
        return 2
    api_key = os.environ.get(API_KEY_ENV, "")
    if not api_key:
        print(f"{API_KEY_ENV} is required", file=sys.stderr)
        return 2

    options = SmokeOptions(
        base_url=args.base_url,
        chat_model=args.chat_model,
        samples=args.samples,
        timeout=args.timeout,
        first_token_target_ms=args.first_token_target_ms,
        embedding_model=args.embedding_model,
        embedding_dimensions=args.embedding_dimensions,
    )
    provider = OpenAICompatibleProvider(
        base_url=options.base_url,
        api_key=api_key,
        timeout_seconds=options.timeout,
    )
    try:
        report = asyncio.run(run_smoke(provider, options))
    except AppError as exc:
        write_report(
            {
                "kind": "real_openai_compatible_provider_smoke",
                "recorded_at": datetime.now(UTC).isoformat(),
                "error": {"code": exc.code, "detail": exc.detail},
                "passed": False,
            },
            args.output,
        )
        return 1
    except (OSError, RuntimeError, ValueError) as exc:
        write_report(
            {
                "kind": "real_openai_compatible_provider_smoke",
                "recorded_at": datetime.now(UTC).isoformat(),
                "error": {"code": "smoke_failed", "detail": str(exc)},
                "passed": False,
            },
            args.output,
        )
        return 1

    write_report(report, args.output)
    return 1 if args.enforce and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
