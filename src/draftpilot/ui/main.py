"""NiceGUI entrypoint.

``from nicegui import app`` is the underlying FastAPI app, so DB / Redis / ARQ
resources are initialized in ``app.on_startup`` and released in
``app.on_shutdown``. Run with ``python -m draftpilot.ui.main``.
"""

from pathlib import Path

import logfire
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from nicegui import app, ui

from draftpilot.api import router as api_router
from draftpilot.core import telemetry
from draftpilot.core.api_auth import open_api_warning
from draftpilot.core.cache import close_redis, get_redis
from draftpilot.core.config import settings
from draftpilot.core.db import create_db_and_tables, dispose_engine
from draftpilot.core.queue import close_arq_pool, get_arq_pool
from draftpilot.ui.pages import design_system, home, projects, screenplay
from draftpilot.ui.theme import register_assets, with_layout
from draftpilot.ui.theme.layout import FAVICON_ICO

telemetry.setup(ui=True)

_FRONTEND_DIR = Path(__file__).parents[3] / "frontend" / "dist"
_FRONTEND_READY = _FRONTEND_DIR.joinpath("index.html").exists()
_ARTWORK_DIR = settings.backup.root / "artwork"
_ARTWORK_DIR.mkdir(parents=True, exist_ok=True)
app.include_router(api_router)


@app.get("/health", include_in_schema=False)
async def health() -> JSONResponse:
    """Report that the UI process is ready to accept HTTP requests."""
    return JSONResponse({"status": "ok"})

if _FRONTEND_READY:
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIR / "assets"), name="frontend-assets")
    app.mount("/artwork", StaticFiles(directory=_ARTWORK_DIR), name="project-artwork")

    @app.get("/{path:path}")
    async def _frontend_fallback(path: str) -> FileResponse:
        """Serve an SPA route or its static file from the built frontend."""
        requested = _FRONTEND_DIR / path
        target = requested if requested.is_file() else _FRONTEND_DIR / "index.html"
        return FileResponse(target)


# --- Routes -------------------------------------------------------------------
if not _FRONTEND_READY:
    ui.page("/")(with_layout(home.content))
    ui.page("/projects")(with_layout(projects.content))
    ui.page("/screenplay/{screenplay_id}")(with_layout(screenplay.content))
    ui.page("/design-system")(with_layout(design_system.content))


# --- Lifecycle ----------------------------------------------------------------
@app.on_startup
async def _startup() -> None:
    """Mount assets, warm shared pools, and ensure dev tables exist."""
    register_assets()
    if warning := open_api_warning(settings.ui.host):
        logfire.warning(warning)
    # Warm shared pools and ensure dev tables exist (Alembic owns production).
    get_redis()
    await get_arq_pool()
    try:
        await create_db_and_tables()
    except Exception as exc:  # noqa: BLE001 - dev convenience only
        logfire.warning("create_db_and_tables skipped: {exc}", exc=str(exc))


@app.on_shutdown
async def _shutdown() -> None:
    """Release the ARQ pool, Redis connection, and database engine."""
    await close_arq_pool()
    await close_redis()
    await dispose_engine()


def main() -> None:
    """Launch the NiceGUI server with the configured runtime settings."""
    ui.run(
        host=settings.ui.host,
        port=settings.ui.port,
        title=settings.ui.title,
        favicon=str(FAVICON_ICO),
        storage_secret=settings.ui.storage_secret.get_secret_value(),
        reload=settings.ui.reload,
        show=False,
    )


# NiceGUI requires ui.run() at module top-level (not behind __main__) so that
# `python -m draftpilot.ui.main` and the auto-reload mechanism both work.
main()
