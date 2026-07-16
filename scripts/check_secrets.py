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
        return [root / item.decode() for item in result.stdout.split(b"\0") if item]
    except (FileNotFoundError, subprocess.CalledProcessError):
        return [
            path
            for path in root.rglob("*")
            if path.is_file()
            and not SKIP_PARTS.intersection(path.relative_to(root).parts)
            and path.name != ".env"
        ]


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
    findings: list[str] = []
    for path in repository_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for finding in scan_text(text):
            findings.append(f"{path.relative_to(ROOT)}:{finding}")
    if findings:
        raise SystemExit("Potential secrets found:\n" + "\n".join(findings))
    print("Secret scan passed.")


if __name__ == "__main__":
    main()
