import json

import pytest

from scripts.performance_baseline import parse_completed_sse, percentile


def test_percentile_uses_nearest_rank() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0, 100.0], 0.95) == 100.0
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.50) == 2.0
    with pytest.raises(ValueError, match="at least one sample"):
        percentile([], 0.95)


def test_parse_completed_sse_rejects_missing_and_error_events() -> None:
    completed = {"id": "message-1", "content": "ok", "citations": []}
    payload = (
        'event: message.started\ndata: {"message_id":"message-1"}\n\n'
        f"event: message.completed\ndata: {json.dumps(completed)}\n\n"
    )
    assert parse_completed_sse(payload) == completed
    with pytest.raises(RuntimeError, match="did not contain"):
        parse_completed_sse('event: message.started\ndata: {"message_id":"x"}\n\n')
    with pytest.raises(RuntimeError, match=r"message\.error"):
        parse_completed_sse('event: message.error\ndata: {"code":"failed"}\n\n')
