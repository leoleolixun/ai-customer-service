import json

import pytest

from scripts.smoke_v1 import normalize_base_url, parse_completed_message


def test_smoke_base_url_accepts_only_an_http_origin() -> None:
    assert normalize_base_url("https://support.example.com/") == "https://support.example.com"

    with pytest.raises(ValueError):
        normalize_base_url("https://user:password@support.example.com/path?target=other")


def test_smoke_sse_parser_returns_the_completed_message() -> None:
    completed = {"id": "message-1", "content": "answer", "citations": [{"id": "c-1"}]}
    payload = "\n\n".join(
        [
            'event: message.started\ndata: {"message_id":"message-1"}',
            'event: message.delta\ndata: {"delta":"answer"}',
            f"event: message.completed\ndata: {json.dumps(completed)}",
            "",
        ]
    )

    assert parse_completed_message(payload) == completed


def test_smoke_sse_parser_rejects_stream_errors() -> None:
    with pytest.raises(RuntimeError, match="provider_failed"):
        parse_completed_message(
            'event: message.error\ndata: {"code":"provider_failed","message":"failed"}\n\n'
        )
