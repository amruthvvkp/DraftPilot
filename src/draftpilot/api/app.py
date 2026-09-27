"""FastAPI application factory: the versioned API plus the built React studio.

Run with ``python -m draftpilot.api``. Alembic owns the schema (compose runs a ``migrate``
service first), so startup never creates tables.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import logfire
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from draftpilot.api import router as api_router
from draftpilot.core import telemetry
from draftpilot.core.api_auth import open_api_warning
from draftpilot.core.cache import close_redis, get_redis
from draftpilot.core.config import settings
from draftpilot.core.db import dispose_engine
from draftpilot.core.queue import close_arq_pool, get_arq_pool


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Warm shared pools on startup and release them on shutdown."""
    if warning := open_api_warning(settings.web.host):
        logfire.warning(warning)
    get_redis()
    await get_arq_pool()
    try:
        yield
    finally:
        await close_arq_pool()
        await close_redis()
        await dispose_engine()


def _spa_file(dist: Path, path: str) -> Path:
    """Resolve a request path to a built asset, or to ``index.html`` for client routes."""
    root = dist.resolve()
    candidate = (root / path).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        return candidate
    return root / "index.html"


def create_app(frontend_dist: Path | None = None) -> FastAPI:
    """Build the web application: API routes, health, artwork, and the SPA fallback."""
    dist = frontend_dist if frontend_dist is not None else settings.web.frontend_dist
    telemetry.setup(web=True)
    app = FastAPI(title=settings.web.title, version=settings.metadata.version, lifespan=lifespan)
    telemetry.instrument_app(app)
    app.include_router(api_router)

    @app.get("/health", include_in_schema=False)
    async def health() -> JSONResponse:
        """Report that the web process is ready to accept HTTP requests."""
        return JSONResponse({"status": "ok"})

    artwork = settings.backup.root / "artwork"
    artwork.mkdir(parents=True, exist_ok=True)
    app.mount("/artwork", StaticFiles(directory=artwork), name="project-artwork")

    if (dist / "index.html").is_file():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="frontend-assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def frontend(path: str) -> FileResponse:
            """Serve a built file, or the SPA shell for client-side routes."""
            if path.startswith("api/"):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
            return FileResponse(_spa_file(dist, path))
    else:
        logfire.warning(
            "React studio build not found at {dist}; run `npm --prefix frontend run build`",
            dist=str(dist),
        )

    return app
