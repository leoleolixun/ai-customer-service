from pathlib import Path

import pytest

from examples.widget_host import main as widget_host


def test_widget_host_injects_runtime_platform_and_application(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        '<ai-support-widget id="support-widget"></ai-support-widget>',
        encoding="utf-8",
    )
    monkeypatch.setattr(widget_host, "demo_dist", dist)
    monkeypatch.setattr(widget_host, "platform_url", "https://support.example.com")
    monkeypatch.setattr(widget_host, "application_id", "application-123")

    response = widget_host.demo_page("")
    content = bytes(response.body).decode()

    assert 'base-url="https://support.example.com"' in content
    assert 'application-id="application-123"' in content
