from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from app import main


def test_docker_build_context_excludes_local_secrets_and_generated_assets() -> None:
    patterns = {
        line.strip()
        for line in Path(".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert ".env" in patterns
    assert ".env.*" in patterns
    assert ".git" in patterns
    assert ".venv" in patterns
    assert "**/node_modules" in patterns
    assert "eval/runs" in patterns
    assert "playwright-report" in patterns


async def test_release_assets_mount_console_demo_sdk_and_widget(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    admin_dist = tmp_path / "apps" / "admin" / "dist"
    assets = admin_dist / "assets"
    sdk = tmp_path / "packages" / "sdk" / "dist"
    widget = tmp_path / "packages" / "widget" / "dist"
    demo = tmp_path / "apps" / "demo" / "dist"
    assets.mkdir(parents=True)
    sdk.mkdir(parents=True)
    widget.mkdir(parents=True)
    demo.mkdir(parents=True)
    (admin_dist / "index.html").write_text("<h1>Support Console</h1>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('admin')", encoding="utf-8")
    (sdk / "index.js").write_text("export class SupportClient {}", encoding="utf-8")
    (widget / "ai-support-widget.js").write_text("customElements.define", encoding="utf-8")
    (demo / "index.html").write_text("<h1>Support Demo</h1>", encoding="utf-8")
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    app = FastAPI()
    main.mount_release_assets(app)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://release.test"
    ) as client:
        root = await client.get("/", follow_redirects=False)
        console = await client.get("/console/handoffs")
        admin_asset = await client.get("/console/assets/app.js")
        demo_page = await client.get("/demo/")
        sdk_asset = await client.get("/sdk/index.js")
        widget_asset = await client.get("/widget/ai-support-widget.js")

    assert root.status_code == 307
    assert root.headers["location"] == "/console/"
    assert console.status_code == 200
    assert "Support Console" in console.text
    assert admin_asset.status_code == 200
    assert demo_page.status_code == 200
    assert "Support Demo" in demo_page.text
    assert sdk_asset.status_code == 200
    assert widget_asset.status_code == 200


def test_docker_image_builds_and_copies_the_demo_site() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "npm run build --workspace @ai-support/demo" in dockerfile
    assert "COPY --from=frontend /src/apps/demo/dist ./apps/demo/dist" in dockerfile
