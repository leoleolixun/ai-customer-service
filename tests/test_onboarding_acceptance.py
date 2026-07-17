from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.onboarding_acceptance import (
    MAX_DURATION_SECONDS,
    OnboardingAcceptanceError,
    RepositoryState,
    create_finish_record,
    create_start_record,
)

COMMIT = "a" * 40
DIGEST = f"sha256:{'b' * 64}"
STARTED_AT = datetime(2026, 7, 17, 8, 0, tzinfo=UTC)


def _state() -> dict[str, Any]:
    return create_start_record(
        reviewer="Independent Developer",
        image_digest=DIGEST,
        repository=RepositoryState(commit=COMMIT, clean=True),
        started_at=STARTED_AT,
    )


def _finish(**overrides: object) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "state": _state(),
        "repository": RepositoryState(commit=COMMIT, clean=True),
        "finished_at": STARTED_AT + timedelta(minutes=12),
        "page_url": "https://host.example.test/help",
        "page_html": (
            '<ai-support-widget id="support"></ai-support-widget>'
            '<script src="https://support.example.test/widget/ai-support-widget.js"></script>'
        ),
        "conversation_id": "8c461dcb-18c1-4ca9-b8ad-44fbcf0f0d99",
        "desktop_evidence_path": Path("widget-conversation-desktop.png"),
        "desktop_evidence_content": b"independent desktop visual evidence",
        "mobile_evidence_path": Path("widget-conversation-mobile.png"),
        "mobile_evidence_content": b"independent mobile visual evidence",
        "widget_bundle_contents": {
            "https://support.example.test/widget/ai-support-widget.js": b"widget bundle",
        },
    }
    arguments.update(overrides)
    return create_finish_record(**arguments)


def test_records_a_complete_integration_within_thirty_minutes() -> None:
    report = _finish()

    assert report["result"] == "passed"
    assert report["duration_seconds"] == 720
    assert report["checks"]["application_secret_absent_from_page_source"] is True
    assert report["visual_evidence"]["desktop"]["sha256"]
    assert report["visual_evidence"]["mobile_375px"]["sha256"]


def test_rejects_an_integration_that_exceeds_thirty_minutes() -> None:
    with pytest.raises(OnboardingAcceptanceError, match="requires at most"):
        _finish(finished_at=STARTED_AT + timedelta(seconds=MAX_DURATION_SECONDS + 1))


@pytest.mark.parametrize(
    "page_html, expected_error",
    [
        ("<html></html>", "does not contain ai-support-widget"),
        ("<ai-support-widget></ai-support-widget>", "does not load the standalone Widget"),
        (
            "<ai-support-widget></ai-support-widget>"
            '<script src="/widget/ai-support-widget.js"></script>'
            '<script>const application_api_key = "acs_secret-value";</script>',
            "expose an application Secret",
        ),
    ],
)
def test_rejects_incomplete_or_unsafe_host_markup(page_html: str, expected_error: str) -> None:
    with pytest.raises(OnboardingAcceptanceError, match=expected_error):
        _finish(page_html=page_html)


def test_requires_the_same_clean_candidate_at_finish() -> None:
    with pytest.raises(OnboardingAcceptanceError, match="candidate changed"):
        _finish(repository=RepositoryState(commit="c" * 40, clean=True))

    with pytest.raises(OnboardingAcceptanceError, match="tracked changes"):
        _finish(repository=RepositoryState(commit=COMMIT, clean=False))


@pytest.mark.parametrize("missing_field", ["desktop_evidence_content", "mobile_evidence_content"])
def test_requires_both_desktop_and_mobile_visual_evidence(missing_field: str) -> None:
    with pytest.raises(OnboardingAcceptanceError, match="must both be non-empty"):
        _finish(**{missing_field: b""})


def test_requires_the_referenced_widget_bundle_to_be_reachable() -> None:
    with pytest.raises(OnboardingAcceptanceError, match="reachable and non-empty"):
        _finish(widget_bundle_contents={})
