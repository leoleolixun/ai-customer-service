import json
from pathlib import Path

import pytest

from scripts.human_review_server import (
    ReviewServer,
    ReviewStore,
    verify_expected_sha256,
    worksheet_sha256,
)

ALLOCATION = {
    "answerable": 18,
    "no_answer": 3,
    "conflict_or_stale": 3,
    "handoff": 3,
    "prompt_injection_or_unauthorized": 3,
}


def _write_worksheet(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for category, count in ALLOCATION.items():
        for index in range(count):
            records.append(
                {
                    "case_id": f"{category}-{index}",
                    "category": category,
                    "tenant_id": "demo-retail",
                    "application_id": "storefront-widget",
                    "risk": {"level": "low", "tags": []},
                    "question": "Question",
                    "answer": "Answer",
                    "expected_evidence": [],
                    "retrieved_sources": [],
                    "cited_sources": [],
                    "cited_evidence": [],
                    "review": {
                        "reviewer": "",
                        "factually_correct": None,
                        "citations_supported": None,
                        "severe_error": None,
                        "notes": "",
                    },
                }
            )
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    return records


def test_review_server_renders_candidate_and_verified_worksheet_digest(tmp_path: Path) -> None:
    worksheet = tmp_path / "human-review.jsonl"
    _write_worksheet(worksheet)
    digest = worksheet_sha256(worksheet)
    server = ReviewServer(
        ("127.0.0.1", 0),
        ReviewStore(worksheet),
        candidate="9c34121",
        worksheet_sha256=digest,
    )

    try:
        page = server.page()
    finally:
        server.server_close()

    assert "候选 9c34121" in page
    assert f"工作表 {digest[:12]}" in page
    assert "__CANDIDATE__" not in page
    assert "__WORKSHEET_SHA__" not in page


def test_review_store_persists_only_complete_validated_updates(tmp_path: Path) -> None:
    worksheet = tmp_path / "human-review.jsonl"
    records = _write_worksheet(worksheet)
    store = ReviewStore(worksheet)
    updates = []
    for record in records:
        answerable = record["category"] == "answerable"
        updates.append(
            {
                "case_id": record["case_id"],
                "review": {
                    "reviewer": "Independent Reviewer",
                    "factually_correct": True if answerable else None,
                    "citations_supported": True if answerable else None,
                    "severe_error": False,
                    "notes": "Checked against the supplied evidence.",
                },
            }
        )

    status = store.save(updates, finalize=True)
    reloaded = ReviewStore(worksheet)

    assert status["ready"] is True
    assert status["completed"] == 30
    assert reloaded.snapshot()["status"]["ready"] is True
    assert worksheet.stat().st_mode & 0o777 == 0o600


def test_review_store_rejects_incomplete_category_allocation(tmp_path: Path) -> None:
    worksheet = tmp_path / "human-review.jsonl"
    records = _write_worksheet(worksheet)
    worksheet.write_text(
        "".join(json.dumps(record) + "\n" for record in records[:-1]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly 30 records"):
        ReviewStore(worksheet)


def test_expected_digest_must_be_well_formed_and_match() -> None:
    actual = "a" * 64

    verify_expected_sha256(actual, None)
    verify_expected_sha256(actual, actual.upper())
    with pytest.raises(ValueError, match="64 hexadecimal"):
        verify_expected_sha256(actual, "not-a-digest")
    with pytest.raises(ValueError, match="mismatch"):
        verify_expected_sha256(actual, "b" * 64)
