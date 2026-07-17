from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import UUID, uuid4

import httpx

STATE_VERSION = 1
MAX_DURATION_SECONDS = 30 * 60
IMAGE_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SECRET_PATTERNS = (
    re.compile(r"\bacs_[A-Za-z0-9._-]{8,}"),
    re.compile(r"X-API-Key", re.IGNORECASE),
    re.compile(r"application[_-]?api[_-]?key", re.IGNORECASE),
)


class OnboardingAcceptanceError(ValueError):
    """Raised when onboarding evidence cannot satisfy the V1 acceptance contract."""


class _WidgetMarkupParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.has_widget_element = False
        self.script_sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "ai-support-widget":
            self.has_widget_element = True
        if tag.lower() != "script":
            return
        attributes = dict(attrs)
        source = attributes.get("src")
        if source:
            self.script_sources.append(source)


@dataclass(frozen=True)
class RepositoryState:
    commit: str
    clean: bool


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise OnboardingAcceptanceError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise OnboardingAcceptanceError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise OnboardingAcceptanceError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _repository_state() -> RepositoryState:
    git = shutil.which("git")
    if git is None:
        raise OnboardingAcceptanceError("git is required to inspect the frozen candidate")
    try:
        commit = subprocess.run(  # noqa: S603 - executable resolved by shutil.which
            [git, "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tracked_changes = subprocess.run(  # noqa: S603 - executable resolved by shutil.which
            [git, "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise OnboardingAcceptanceError("unable to inspect the frozen Git candidate") from exc
    return RepositoryState(commit=commit, clean=not tracked_changes)


def create_start_record(
    *,
    reviewer: str,
    image_digest: str,
    repository: RepositoryState,
    started_at: datetime,
) -> dict[str, Any]:
    normalized_reviewer = reviewer.strip()
    if not normalized_reviewer:
        raise OnboardingAcceptanceError("reviewer must identify the independent integrator")
    if not IMAGE_DIGEST_PATTERN.fullmatch(image_digest):
        raise OnboardingAcceptanceError("image_digest must be a complete sha256 digest")
    if not repository.clean:
        raise OnboardingAcceptanceError("the acceptance checkout must have no tracked changes")
    return {
        "schema_version": STATE_VERSION,
        "run_id": str(uuid4()),
        "reviewer": normalized_reviewer,
        "git_commit": repository.commit,
        "image_digest": image_digest,
        "started_at": started_at.astimezone(UTC).isoformat(),
    }


def _validate_page(page_url: str, page_html: str) -> list[str]:
    parsed_url = urlparse(page_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise OnboardingAcceptanceError("page_url must be an absolute HTTP(S) URL")
    for pattern in SECRET_PATTERNS:
        if pattern.search(page_html):
            raise OnboardingAcceptanceError("the host page appears to expose an application Secret")

    parser = _WidgetMarkupParser()
    parser.feed(page_html)
    if not parser.has_widget_element:
        raise OnboardingAcceptanceError("the host page does not contain ai-support-widget")
    widget_sources = [
        urljoin(page_url, source)
        for source in parser.script_sources
        if "ai-support-widget" in source or "/widget/" in source
    ]
    if not widget_sources:
        raise OnboardingAcceptanceError("the host page does not load the standalone Widget bundle")
    return widget_sources


def create_finish_record(
    *,
    state: dict[str, Any],
    repository: RepositoryState,
    finished_at: datetime,
    page_url: str,
    page_html: str,
    conversation_id: str,
    desktop_evidence_path: Path,
    desktop_evidence_content: bytes,
    mobile_evidence_path: Path,
    mobile_evidence_content: bytes,
    widget_bundle_contents: dict[str, bytes],
) -> dict[str, Any]:
    if state.get("schema_version") != STATE_VERSION:
        raise OnboardingAcceptanceError("unsupported onboarding acceptance state version")
    reviewer = state.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise OnboardingAcceptanceError("state does not identify an independent integrator")
    if repository.commit != state.get("git_commit"):
        raise OnboardingAcceptanceError("the Git candidate changed during the timed integration")
    if not repository.clean:
        raise OnboardingAcceptanceError("the acceptance checkout has tracked changes")
    try:
        UUID(conversation_id)
    except ValueError as exc:
        raise OnboardingAcceptanceError(
            "conversation_id must be the completed platform conversation UUID"
        ) from exc
    if not desktop_evidence_content or not mobile_evidence_content:
        raise OnboardingAcceptanceError("desktop and mobile visual evidence must both be non-empty")

    started_at = _parse_timestamp(state.get("started_at"), "started_at")
    normalized_finished_at = finished_at.astimezone(UTC)
    duration_seconds = (normalized_finished_at - started_at).total_seconds()
    if duration_seconds < 0:
        raise OnboardingAcceptanceError("finished_at is earlier than started_at")
    if duration_seconds > MAX_DURATION_SECONDS:
        raise OnboardingAcceptanceError(
            f"integration took {duration_seconds:.3f}s; V1 requires at most {MAX_DURATION_SECONDS}s"
        )
    widget_sources = _validate_page(page_url, page_html)
    if any(not widget_bundle_contents.get(source) for source in widget_sources):
        raise OnboardingAcceptanceError(
            "every standalone Widget bundle must be reachable and non-empty"
        )
    return {
        **state,
        "finished_at": normalized_finished_at.isoformat(),
        "duration_seconds": round(duration_seconds, 3),
        "page_url": page_url,
        "widget_script_urls": widget_sources,
        "conversation_id": conversation_id,
        "visual_evidence": {
            "desktop": {
                "filename": desktop_evidence_path.name,
                "sha256": hashlib.sha256(desktop_evidence_content).hexdigest(),
                "byte_size": len(desktop_evidence_content),
            },
            "mobile_375px": {
                "filename": mobile_evidence_path.name,
                "sha256": hashlib.sha256(mobile_evidence_content).hexdigest(),
                "byte_size": len(mobile_evidence_content),
            },
        },
        "checks": {
            "within_30_minutes": True,
            "host_page_reachable": True,
            "widget_markup_present": True,
            "standalone_widget_bundle_present": True,
            "standalone_widget_bundle_reachable": True,
            "application_secret_absent_from_page_source": True,
            "completed_conversation_recorded": True,
            "desktop_visual_evidence_recorded": True,
            "mobile_375px_visual_evidence_recorded": True,
        },
        "result": "passed",
    }


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OnboardingAcceptanceError(f"unable to read JSON state: {path}") from exc
    if not isinstance(value, dict):
        raise OnboardingAcceptanceError("the onboarding state must be a JSON object")
    return value


def _write_new_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
    except FileExistsError as exc:
        raise OnboardingAcceptanceError(f"refusing to overwrite existing evidence: {path}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record independently executed V1 Widget onboarding acceptance evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="freeze identity and start the 30-minute timer")
    start.add_argument("--reviewer", required=True)
    start.add_argument("--image-digest", required=True)
    start.add_argument("--output", type=Path, required=True)

    finish = subparsers.add_parser("finish", help="verify the host page and finish the timer")
    finish.add_argument("--state", type=Path, required=True)
    finish.add_argument("--page-url", required=True)
    finish.add_argument("--conversation-id", required=True)
    finish.add_argument("--desktop-evidence", type=Path, required=True)
    finish.add_argument("--mobile-evidence", type=Path, required=True)
    finish.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    try:
        repository = _repository_state()
        if args.command == "start":
            record = create_start_record(
                reviewer=args.reviewer,
                image_digest=args.image_digest,
                repository=repository,
                started_at=_utc_now(),
            )
            _write_new_json(args.output, record)
            print(f"onboarding timer started: {record['run_id']}")
            return

        state = _load_json_object(args.state)
        desktop_evidence_content = args.desktop_evidence.read_bytes()
        mobile_evidence_content = args.mobile_evidence.read_bytes()
        response = httpx.get(args.page_url, follow_redirects=True, timeout=10)
        response.raise_for_status()
        page_url = str(response.url)
        widget_bundle_contents: dict[str, bytes] = {}
        for widget_source in _validate_page(page_url, response.text):
            bundle_response = httpx.get(widget_source, follow_redirects=True, timeout=10)
            bundle_response.raise_for_status()
            widget_bundle_contents[widget_source] = bundle_response.content
        record = create_finish_record(
            state=state,
            repository=repository,
            finished_at=_utc_now(),
            page_url=page_url,
            page_html=response.text,
            conversation_id=args.conversation_id,
            desktop_evidence_path=args.desktop_evidence,
            desktop_evidence_content=desktop_evidence_content,
            mobile_evidence_path=args.mobile_evidence,
            mobile_evidence_content=mobile_evidence_content,
            widget_bundle_contents=widget_bundle_contents,
        )
        _write_new_json(args.output, record)
        print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))
    except (OnboardingAcceptanceError, OSError, httpx.HTTPError) as exc:
        raise SystemExit(f"onboarding acceptance failed: {exc}") from exc


if __name__ == "__main__":
    main()
