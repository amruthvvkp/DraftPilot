"""FastAPI application factory: the versioned API plus the built React studio.

Run with ``python -m draftpilot.api``. Alembic owns the schema (compose runs a ``migrate``
service first), so startup never creates tables.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import logfire
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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


IMMUTABLE = "public, max-age=31536000, immutable"


class StaticCacheMiddleware:
    """Cache hashed Vite assets forever and make browsers revalidate the SPA shell."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Set ``Cache-Control`` on successful asset and HTML-shell responses."""
        path = scope.get("path", "")
        if scope["type"] != "http" or path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        async def send_with_cache(message: Message) -> None:
            """Add the cache header to the response start when it applies."""
            if message["type"] == "http.response.start" and message["status"] == 200:
                headers = MutableHeaders(scope=message)
                if path.startswith("/assets/"):
                    headers["Cache-Control"] = IMMUTABLE
                elif headers.get("content-type", "").startswith("text/html"):
                    headers["Cache-Control"] = "no-cache"
            await send(message)

        await self.app(scope, receive, send_with_cache)


def create_app(frontend_dist: Path | None = None) -> FastAPI:
    """Build the web application: API routes, health, artwork, and the React studio."""
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

    @app.api_route("/api/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def api_not_found(path: str) -> None:
        """Answer unmatched API paths with 404 so the SPA fallback never shadows them."""
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # FastAPI routes win; the build is checked only when nothing else matched.
    if settings.web.require_frontend or (dist / "index.html").is_file():
        app.frontend(
            "/", directory=dist, fallback="index.html", check_dir=settings.web.require_frontend
        )
    else:
        logfire.warning(
            "React studio build not found at {dist}; run `npm --prefix frontend run build`",
            dist=str(dist),
        )
    app.add_middleware(StaticCacheMiddleware)

    return app
