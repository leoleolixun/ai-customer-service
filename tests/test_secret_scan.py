import shutil
import subprocess
from pathlib import Path

from scripts.check_secrets import repository_files, scan_text


def test_secret_scanner_detects_high_confidence_credentials() -> None:
    assert scan_text("token=" + "sk-" + "abcdefghijklmnopqrstuvwxyz123456")
    assert scan_text("-----BEGIN " + "PRIVATE KEY-----")
    assert scan_text("key=" + "AKIA" + "ABCDEFGHIJKLMNOP")


def test_secret_scanner_allows_templates_and_explicit_test_fixture() -> None:
    assert not scan_text("APP_API_KEY=replace-me")
    test_key = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    assert not scan_text(f"token={test_key} # allow-secret-scan")


def test_secret_scanner_includes_untracked_nonignored_files(tmp_path: Path) -> None:
    git = shutil.which("git")
    assert git is not None
    subprocess.run(  # noqa: S603 - executable resolved from PATH, arguments fixed
        [git, "init", "--quiet"], cwd=tmp_path, check=True
    )
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "tracked.txt").write_text("tracked", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("untracked", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("ignored", encoding="utf-8")
    subprocess.run(  # noqa: S603 - executable resolved from PATH, arguments fixed
        [git, "add", ".gitignore", "tracked.txt"], cwd=tmp_path, check=True
    )

    files = {path.relative_to(tmp_path).as_posix() for path in repository_files(tmp_path)}

    assert files == {".gitignore", "tracked.txt", "untracked.txt"}
