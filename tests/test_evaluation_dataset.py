from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "eval" / "rag_v1.jsonl"
CORPUS_PATH = ROOT / "eval" / "knowledge_sources_v1.jsonl"


class EvaluationModule(Protocol):
    EvaluationError: type[ValueError]

    def load_jsonl(self, path: Path) -> list[dict[str, Any]]: ...

    def validate_dataset(
        self,
        cases: list[dict[str, Any]],
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    def score_predictions(
        self,
        cases: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        predictions: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


def _load_evaluator() -> EvaluationModule:
    spec = spec_from_file_location("rag_evaluation_tool", ROOT / "scripts" / "evaluate_rag.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load RAG evaluation tool")
    module: ModuleType = module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(EvaluationModule, module)


EVALUATOR = _load_evaluator()


def _load_fixed_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return EVALUATOR.load_jsonl(DATASET_PATH), EVALUATOR.load_jsonl(CORPUS_PATH)


def _oracle_predictions_for_calculator_test(
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build deterministic unit-test input; this is not a persisted model baseline."""
    predictions: list[dict[str, Any]] = []
    review_targets = {
        "answerable": 18,
        "no_answer": 3,
        "conflict_or_stale": 3,
        "handoff": 3,
        "prompt_injection_or_unauthorized": 3,
    }
    reviewed_by_category = {category: 0 for category in review_targets}
    for case in cases:
        answer = ""
        cited_sources: list[str] = []
        if case["primary_category"] == "answerable":
            answer = ";".join(str(fact["match_any"][0]) for fact in case["key_facts"])
            cited_sources = list(case["expected_sources"])
        elif case["should_handoff"]:
            answer = "这个请求需要人工处理, 已为你转接。"
        else:
            answer = "现有知识无法可靠确认, 因此不能给出确定答复。"

        prediction: dict[str, Any] = {
            "case_id": case["id"],
            "answer": answer,
            "retrieved_sources": list(case["expected_sources"]),
            "cited_sources": cited_sources,
            "source_tenants": {
                source_id: case["tenant_id"] for source_id in case["expected_sources"]
            },
            "refused": bool(case["should_refuse"]),
            "handoff": bool(case["should_handoff"]),
        }
        category = str(case["primary_category"])
        if reviewed_by_category[category] < review_targets[category]:
            prediction["review"] = {
                "reviewer": "unit-test-reviewer",
                "factually_correct": True if category == "answerable" else None,
                "citations_supported": True if category == "answerable" else None,
                "severe_error": False,
                "notes": "Calculator-only fixture.",
            }
            reviewed_by_category[category] += 1
        predictions.append(prediction)
    return predictions


def test_fixed_v1_dataset_meets_distribution_and_integrity_rules() -> None:
    cases, sources = _load_fixed_data()

    summary = EVALUATOR.validate_dataset(cases, sources)

    assert summary == {
        "dataset_version": "1.0.0",
        "case_count": 150,
        "source_count": 22,
        "category_counts": {
            "answerable": 90,
            "conflict_or_stale": 10,
            "handoff": 10,
            "no_answer": 30,
            "prompt_injection_or_unauthorized": 10,
        },
        "should_refuse_count": 60,
        "should_handoff_count": 10,
    }
    assert len({case["question"] for case in cases}) == 150


def test_dataset_validation_rejects_cross_tenant_expected_source() -> None:
    cases, sources = _load_fixed_data()
    invalid_cases = deepcopy(cases)
    invalid_cases[0]["expected_sources"] = ["saas/trial-v1"]

    with pytest.raises(EVALUATOR.EvaluationError, match="another tenant"):
        EVALUATOR.validate_dataset(invalid_cases, sources)


def test_metric_calculator_reports_all_required_metrics_and_release_gate() -> None:
    cases, sources = _load_fixed_data()
    predictions = _oracle_predictions_for_calculator_test(cases)

    report = EVALUATOR.score_predictions(cases, sources, predictions)

    assert report["prediction_coverage"]["value"] == 1.0
    assert report["metrics"]["recall_at_20"]["value"] == 1.0
    assert report["metrics"]["hit_at_5"]["value"] == 1.0
    assert report["metrics"]["key_fact_accuracy"]["value"] == 1.0
    assert report["metrics"]["citation_support_rate"]["value"] == 1.0
    assert report["metrics"]["no_answer_refusal_rate"]["value"] == 1.0
    assert report["metrics"]["handoff_recognition_rate"]["value"] == 1.0
    assert report["metrics"]["severe_errors"]["count"] == 0
    assert report["manual_review"]["reviewed"] == 30
    assert report["release_gate"]["passed"] is True


def test_metric_calculator_does_not_hide_missing_or_unsafe_predictions() -> None:
    cases, sources = _load_fixed_data()
    predictions = _oracle_predictions_for_calculator_test(cases)
    unsafe = next(item for item in predictions if item["case_id"] == "rag-v1-handoff-001")
    unsafe.update(
        {
            "answer": "系统已经退款 500 元。",
            "refused": False,
            "handoff": False,
            "review": {
                "reviewer": "security-reviewer",
                "factually_correct": False,
                "citations_supported": False,
                "severe_error": True,
                "notes": "Fabricated a completed refund.",
            },
        }
    )
    predictions.pop()

    report = EVALUATOR.score_predictions(cases, sources, predictions)

    assert report["prediction_coverage"]["value"] < 1.0
    assert report["prediction_coverage"]["missing_case_ids"]
    assert report["metrics"]["handoff_recognition_rate"]["value"] == 0.9
    assert "rag-v1-handoff-001" in report["metrics"]["severe_errors"]["automatic_case_ids"]
    assert "rag-v1-handoff-001" in report["metrics"]["severe_errors"]["reviewer_case_ids"]
    assert report["release_gate"]["passed"] is False


def test_metric_calculator_rejects_duplicate_prediction_ids() -> None:
    cases, sources = _load_fixed_data()
    predictions = _oracle_predictions_for_calculator_test(cases)
    predictions.append(deepcopy(predictions[0]))

    with pytest.raises(EVALUATOR.EvaluationError, match="duplicate case_id"):
        EVALUATOR.score_predictions(cases, sources, predictions)


def test_metric_calculator_accepts_unlisted_source_from_same_tenant() -> None:
    cases, sources = _load_fixed_data()
    predictions = _oracle_predictions_for_calculator_test(cases)
    prediction = predictions[0]
    prediction["retrieved_sources"].append("runtime/same-tenant-document")
    prediction["source_tenants"]["runtime/same-tenant-document"] = cases[0]["tenant_id"]

    report = EVALUATOR.score_predictions(cases, sources, predictions)

    assert report["metrics"]["severe_errors"]["count"] == 0


def test_metric_calculator_detects_declared_cross_tenant_source() -> None:
    cases, sources = _load_fixed_data()
    predictions = _oracle_predictions_for_calculator_test(cases)
    prediction = predictions[0]
    prediction["retrieved_sources"].append("runtime/other-tenant-document")
    prediction["source_tenants"]["runtime/other-tenant-document"] = "another-tenant"

    report = EVALUATOR.score_predictions(cases, sources, predictions)

    assert prediction["case_id"] in report["metrics"]["severe_errors"]["automatic_case_ids"]


def test_metric_calculator_requires_tenant_for_every_source() -> None:
    cases, sources = _load_fixed_data()
    predictions = _oracle_predictions_for_calculator_test(cases)
    predictions[0]["source_tenants"].clear()

    with pytest.raises(EVALUATOR.EvaluationError, match="source_tenants is missing"):
        EVALUATOR.score_predictions(cases, sources, predictions)
