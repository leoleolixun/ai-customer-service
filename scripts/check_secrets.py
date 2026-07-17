import argparse
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "provider key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "application credential": re.compile(r"\bacs_[a-f0-9]{16}\.[A-Za-z0-9_-]{32,}\b"),
}
SKIP_PARTS = {".git", ".venv", "node_modules", "dist", "coverage", "test-results"}
DEPENDENCY_SKIP_PARTS = {".git", ".venv", "node_modules"}
DEFAULT_ARTIFACT_PATHS = (
    "apps/admin/dist",
    "apps/demo/dist",
    "packages/sdk/dist",
    "packages/widget/dist",
    "playwright-report",
    "test-results",
    "eval/runs",
)


def files_under(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for candidate in paths:
        if candidate.is_file():
            files.append(candidate)
            continue
        if not candidate.is_dir():
            continue
        files.extend(
            path
            for path in candidate.rglob("*")
            if path.is_file() and not DEPENDENCY_SKIP_PARTS.intersection(path.parts)
        )
    return files


def repository_files(root: Path = ROOT) -> list[Path]:
    try:
        git = shutil.which("git")
        if git is None:
            raise FileNotFoundError
        result = subprocess.run(  # noqa: S603 - executable resolved from PATH, arguments fixed
            [git, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        repository = [root / item.decode() for item in result.stdout.split(b"\0") if item]
    except (FileNotFoundError, subprocess.CalledProcessError):
        repository = [
            path
            for path in root.rglob("*")
            if path.is_file()
            and not SKIP_PARTS.intersection(path.relative_to(root).parts)
            and path.name != ".env"
        ]
    artifacts = files_under([root / relative for relative in DEFAULT_ARTIFACT_PATHS])
    return list(dict.fromkeys([*repository, *artifacts]))


def scan_text(text: str) -> list[str]:
    findings: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if "allow-secret-scan" in line:
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(line):
                findings.append(f"line {line_number}: {label}")
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan repository and release artifacts for secrets"
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        type=Path,
        help="Additional file or directory to scan; may be repeated",
    )
    args = parser.parse_args()
    findings: list[str] = []
    paths = list(dict.fromkeys([*repository_files(), *files_under(args.path)]))
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for finding in scan_text(text):
            try:
                display_path = path.relative_to(ROOT)
            except ValueError:
                display_path = path
            findings.append(f"{display_path}:{finding}")
    if findings:
        raise SystemExit("Potential secrets found:\n" + "\n".join(findings))
    print("Secret scan passed.")


if __name__ == "__main__":
    main()
