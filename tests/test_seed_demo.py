import io

import pytest
from pytest import MonkeyPatch

from scripts.password_input import read_password


def test_demo_password_can_be_read_from_stdin(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("a-secure-demo-password\n"))

    assert read_password(from_stdin=True) == "a-secure-demo-password"


def test_demo_password_stdin_must_not_be_empty(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    with pytest.raises(SystemExit, match="No password"):
        read_password(from_stdin=True)
