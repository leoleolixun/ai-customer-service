import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]


class HumanReviewModule(Protocol):
    ReviewError: type[ValueError]
    REVIEW_ALLOCATION: dict[str, int]

    def load_jsonl(self, path: Path) -> list[dict[str, Any]]: ...

    def prepare_reviews(
        self,
        cases: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        predictions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...

    def merge_reviews(
        self,
        predictions: list[dict[str, Any]],
        review_records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...


def _load_module() -> HumanReviewModule:
    spec = spec_from_file_location("human_review_tool", ROOT / "scripts" / "human_review.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load human review tool")
    module: ModuleType = module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(HumanReviewModule, module)


TOOL = _load_module()


def _predictions(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": case["id"],
            "answer": "测试回答",
            "retrieved_sources": list(case["expected_sources"]),
            "cited_sources": list(case["expected_sources"]),
            "source_tenants": {
                source_id: case["tenant_id"] for source_id in case["expected_sources"]
            },
            "refused": bool(case["should_refuse"]),
            "handoff": bool(case["should_handoff"]),
        }
        for case in cases
    ]


def _prepared() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases = TOOL.load_jsonl(ROOT / "eval" / "rag_v1.jsonl")
    sources = TOOL.load_jsonl(ROOT / "eval" / "knowledge_sources_v1.jsonl")
    predictions = _predictions(cases)
    return predictions, TOOL.prepare_reviews(cases, sources, predictions)


def test_prepare_reviews_creates_stratified_blank_worksheet() -> None:
    _, worksheet = _prepared()

    assert len(worksheet) == 30
    assert len({record["case_id"] for record in worksheet}) == 30
    assert {
        category: sum(record["category"] == category for record in worksheet)
        for category in TOOL.REVIEW_ALLOCATION
    } == TOOL.REVIEW_ALLOCATION
    assert all(record["review"]["reviewer"] == "" for record in worksheet)
    assert all(record["review"]["severe_error"] is None for record in worksheet)


def test_merge_reviews_requires_completed_independent_fields() -> None:
    predictions, worksheet = _prepared()

    with pytest.raises(TOOL.ReviewError, match="reviewer"):
        TOOL.merge_reviews(predictions, worksheet)


def test_merge_reviews_adds_only_completed_selected_reviews() -> None:
    predictions, worksheet = _prepared()
    for record in worksheet:
        answerable = record["category"] == "answerable"
        record["review"] = {
            "reviewer": "reviewer@example.com",
            "factually_correct": True if answerable else None,
            "citations_supported": True if answerable else None,
            "severe_error": False,
            "notes": "已对照问题、回答和来源。",
        }

    merged = TOOL.merge_reviews(predictions, worksheet)

    assert len(merged) == len(predictions)
    assert sum("review" in prediction for prediction in merged) == 30
    serialized = json.dumps(merged, ensure_ascii=False)
    assert "reviewer@example.com" in serialized
