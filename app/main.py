from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.cache import get_redis
from app.core.config import get_settings
from app.core.cors import PathAwareCORSMiddleware
from app.core.database import engine
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware

settings = get_settings()
configure_logging(settings.log_level)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await get_redis().aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(PathAwareCORSMiddleware, staff_origins=settings.cors_origins)
    register_error_handlers(application)
    application.include_router(health_router)
    application.include_router(v1_router)
    mount_release_assets(application)
    return application


def mount_release_assets(application: FastAPI) -> None:
    admin_dist = PROJECT_ROOT / "apps" / "admin" / "dist"
    admin_index = admin_dist / "index.html"
    if admin_index.is_file():
        assets = admin_dist / "assets"
        if assets.is_dir():
            application.mount(
                "/console/assets",
                StaticFiles(directory=assets),
                name="admin-assets",
            )

        @application.get("/", include_in_schema=False)
        async def release_root() -> RedirectResponse:
            return RedirectResponse(url="/console/", status_code=307)

        @application.get("/console", include_in_schema=False)
        async def console_redirect() -> RedirectResponse:
            return RedirectResponse(url="/console/", status_code=307)

        @application.get("/console/{path:path}", include_in_schema=False)
        async def console_spa(path: str) -> FileResponse:
            del path
            return FileResponse(admin_index)

    for route, relative_path, name in (
        ("/sdk", Path("packages/sdk/dist"), "support-sdk"),
        ("/widget", Path("packages/widget/dist"), "support-widget"),
    ):
        directory = PROJECT_ROOT / relative_path
        if directory.is_dir():
            application.mount(route, StaticFiles(directory=directory), name=name)


app = create_app()
