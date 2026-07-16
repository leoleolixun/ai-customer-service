from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_DATASET = Path("eval/rag_v1.jsonl")
DEFAULT_CORPUS = Path("eval/knowledge_sources_v1.jsonl")
REVIEW_ALLOCATION = {
    "answerable": 18,
    "no_answer": 3,
    "conflict_or_stale": 3,
    "handoff": 3,
    "prompt_injection_or_unauthorized": 3,
}


class ReviewError(ValueError):
    """Raised when a review worksheet cannot be prepared or merged safely."""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ReviewError(f"JSONL file does not exist: {path}")
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ReviewError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ReviewError(f"{path}:{line_number}: each line must be an object")
        records.append(value)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _index(records: list[dict[str, Any]], field: str, label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records, 1):
        value = record.get(field)
        if not isinstance(value, str) or not value:
            raise ReviewError(f"{label} record {index}: {field} must be a non-empty string")
        if value in indexed:
            raise ReviewError(f"{label} record {index}: duplicate {field} {value!r}")
        indexed[value] = record
    return indexed


def _round_robin(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        risk = case.get("risk")
        risk_level = str(risk.get("level", "")) if isinstance(risk, dict) else ""
        group_key = (
            str(case.get("tenant_id", "")),
            str(case.get("application_id", "")),
            risk_level,
        )
        groups[group_key].append(case)
    for group in groups.values():
        group.sort(key=lambda item: str(item["id"]))

    ordered: list[dict[str, Any]] = []
    group_keys = sorted(groups)
    while any(groups.values()):
        for group_key in group_keys:
            group = groups[group_key]
            if group:
                ordered.append(group.pop(0))
    return ordered


def prepare_reviews(
    cases: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    prediction_by_id = _index(predictions, "case_id", "prediction")
    source_by_id = _index(sources, "source_id", "source")
    cases_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        case_id = case.get("id")
        category = case.get("primary_category")
        if not isinstance(case_id, str) or case_id not in prediction_by_id:
            raise ReviewError(f"dataset case {case_id!r} has no prediction")
        if not isinstance(category, str):
            raise ReviewError(f"dataset case {case_id!r} has no primary_category")
        cases_by_category[category].append(case)

    selected: list[dict[str, Any]] = []
    for category, count in REVIEW_ALLOCATION.items():
        candidates = _round_robin(cases_by_category[category])
        if len(candidates) < count:
            raise ReviewError(
                f"category {category!r} requires {count} review cases, found {len(candidates)}"
            )
        selected.extend(candidates[:count])

    worksheet: list[dict[str, Any]] = []
    for case in selected:
        prediction = prediction_by_id[str(case["id"])]
        expected_evidence = [
            {
                "source_id": source_id,
                "title": source_by_id[source_id]["title"],
                "content": source_by_id[source_id]["content"],
                "status": source_by_id[source_id]["status"],
            }
            for source_id in case["expected_sources"]
        ]
        cited_evidence = [
            {
                "source_id": source_id,
                "title": source_by_id[source_id]["title"],
                "content": source_by_id[source_id]["content"],
                "status": source_by_id[source_id]["status"],
            }
            for source_id in prediction["cited_sources"]
            if source_id in source_by_id
        ]
        worksheet.append(
            {
                "case_id": case["id"],
                "category": case["primary_category"],
                "tenant_id": case["tenant_id"],
                "application_id": case["application_id"],
                "risk": case["risk"],
                "question": case["question"],
                "answer": prediction["answer"],
                "expected_evidence": expected_evidence,
                "retrieved_sources": prediction["retrieved_sources"],
                "cited_sources": prediction["cited_sources"],
                "cited_evidence": cited_evidence,
                "review": {
                    "reviewer": "",
                    "factually_correct": None,
                    "citations_supported": None,
                    "severe_error": None,
                    "notes": "",
                },
            }
        )
    return worksheet


def _validated_review(record: dict[str, Any], index: int) -> tuple[str, dict[str, Any]]:
    location = f"review record {index}"
    case_id = record.get("case_id")
    category = record.get("category")
    review = record.get("review")
    if not isinstance(case_id, str) or not case_id:
        raise ReviewError(f"{location}: case_id must be a non-empty string")
    if category not in REVIEW_ALLOCATION:
        raise ReviewError(f"{location}: unsupported category {category!r}")
    if not isinstance(review, dict):
        raise ReviewError(f"{location}: review must be an object")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ReviewError(f"{location}: reviewer must identify the independent reviewer")
    if not isinstance(review.get("severe_error"), bool):
        raise ReviewError(f"{location}: severe_error must be true or false")
    if not isinstance(review.get("notes"), str):
        raise ReviewError(f"{location}: notes must be a string")
    for field in ("factually_correct", "citations_supported"):
        value = review.get(field)
        if value is not None and not isinstance(value, bool):
            raise ReviewError(f"{location}: {field} must be true, false, or null")
        if category == "answerable" and not isinstance(value, bool):
            raise ReviewError(f"{location}: answerable review requires {field}")
    return case_id, {
        "reviewer": reviewer.strip(),
        "factually_correct": review["factually_correct"],
        "citations_supported": review["citations_supported"],
        "severe_error": review["severe_error"],
        "notes": review["notes"].strip(),
    }


def merge_reviews(
    predictions: list[dict[str, Any]], review_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    prediction_by_id = _index(predictions, "case_id", "prediction")
    reviewed_by_category: dict[str, int] = defaultdict(int)
    validated: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(review_records, 1):
        case_id, review = _validated_review(record, index)
        if case_id in validated:
            raise ReviewError(f"review record {index}: duplicate case_id {case_id!r}")
        if case_id not in prediction_by_id:
            raise ReviewError(f"review record {index}: prediction {case_id!r} does not exist")
        validated[case_id] = review
        reviewed_by_category[str(record["category"])] += 1

    for category, required in REVIEW_ALLOCATION.items():
        if reviewed_by_category[category] < required:
            raise ReviewError(
                f"category {category!r} requires {required} completed reviews, "
                f"found {reviewed_by_category[category]}"
            )

    merged: list[dict[str, Any]] = []
    for prediction in predictions:
        result = dict(prediction)
        case_id = str(prediction["case_id"])
        if case_id in validated:
            if "review" in prediction:
                raise ReviewError(
                    f"prediction {case_id!r} already contains a review; use the raw run output"
                )
            result["review"] = validated[case_id]
        merged.append(result)
    return merged


def _ensure_distinct_paths(input_paths: list[Path], output: Path) -> None:
    output_path = output.resolve()
    if any(path.resolve() == output_path for path in input_paths):
        raise ReviewError("output must differ from every input file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and merge independent human reviews for the fixed RAG evaluation."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="create a stratified 30-case worksheet")
    prepare.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    prepare.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    prepare.add_argument("--predictions", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)

    merge = subparsers.add_parser("merge", help="merge completed reviews into raw predictions")
    merge.add_argument("--predictions", type=Path, required=True)
    merge.add_argument("--reviews", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "prepare":
            _ensure_distinct_paths([args.dataset, args.corpus, args.predictions], args.output)
            records = prepare_reviews(
                load_jsonl(args.dataset),
                load_jsonl(args.corpus),
                load_jsonl(args.predictions),
            )
        else:
            _ensure_distinct_paths([args.predictions, args.reviews], args.output)
            records = merge_reviews(
                load_jsonl(args.predictions),
                load_jsonl(args.reviews),
            )
        write_jsonl(args.output, records)
    except ReviewError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote {len(records)} records to {args.output}")


if __name__ == "__main__":
    main()
