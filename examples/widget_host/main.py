import os
from html import escape
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Support Widget Host Example", docs_url=None, redoc_url=None)

platform_url = os.getenv("SUPPORT_PLATFORM_URL", "http://localhost:8000").rstrip("/")
application_api_key = os.getenv("SUPPORT_APPLICATION_API_KEY", "")
application_origin = os.getenv("SUPPORT_APPLICATION_ORIGIN", "http://localhost:8081")
application_id = os.getenv("SUPPORT_APPLICATION_ID", "demo")
demo_user_id = os.getenv("SUPPORT_DEMO_USER_ID", "neutral-demo-user")
demo_dist = Path(__file__).resolve().parents[2] / "apps" / "demo" / "dist"


@app.get("/api/support-token")
async def support_token(request: Request) -> dict[str, object]:
    if not application_api_key:
        raise HTTPException(status_code=503, detail="Support integration is not configured.")
    # A real host must derive this value from its authenticated server-side session.
    external_user_id = demo_user_id
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.post(
                f"{platform_url}/v1/customer-tokens",
                headers={
                    "X-API-Key": application_api_key,
                    "Origin": application_origin,
                    "X-Request-ID": request.headers.get("X-Request-ID", "widget-host"),
                },
                json={"external_user_id": external_user_id},
            )
        response.raise_for_status()
        return dict(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail="The support platform is temporarily unavailable."
        ) from exc


if demo_dist.exists():
    app.mount("/assets", StaticFiles(directory=demo_dist / "assets"), name="demo-assets")


@app.get("/{path:path}", include_in_schema=False)
def demo_page(path: str) -> HTMLResponse:
    del path
    index = demo_dist / "index.html"
    if not index.exists():
        raise HTTPException(status_code=503, detail="Build apps/demo before starting this host.")
    content = index.read_text(encoding="utf-8")
    widget_id = 'id="support-widget"'
    if widget_id not in content:
        raise HTTPException(
            status_code=503, detail="Demo build does not contain the support widget."
        )
    runtime_config = (
        f'{widget_id}\n      base-url="{escape(platform_url, quote=True)}"'
        f'\n      application-id="{escape(application_id, quote=True)}"'
    )
    return HTMLResponse(content.replace(widget_id, runtime_config, 1))
