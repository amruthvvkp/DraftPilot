"""NiceGUI entrypoint.

``from nicegui import app`` is the underlying FastAPI app, so DB / Redis / ARQ
resources are initialized in ``app.on_startup`` and released in
``app.on_shutdown``. Run with ``python -m draftpilot.ui.main``.
"""

import logfire
from nicegui import app, ui

from draftpilot.core import telemetry
from draftpilot.core.cache import close_redis, get_redis
from draftpilot.core.config import settings
from draftpilot.core.db import create_db_and_tables, dispose_engine
from draftpilot.core.queue import close_arq_pool, get_arq_pool
from draftpilot.ui.pages import design_system, home, projects, screenplay
from draftpilot.ui.theme import register_assets, with_layout
from draftpilot.ui.theme.layout import FAVICON_ICO

telemetry.setup(ui=True)


# --- Routes -------------------------------------------------------------------
ui.page("/")(with_layout(home.content))
ui.page("/projects")(with_layout(projects.content))
ui.page("/screenplay/{screenplay_id}")(with_layout(screenplay.content))
ui.page("/design-system")(with_layout(design_system.content))


# --- Lifecycle ----------------------------------------------------------------
@app.on_startup
async def _startup() -> None:
    """Mount assets, warm shared pools, and ensure dev tables exist."""
    register_assets()
    # Warm shared pools and ensure dev tables exist (Alembic owns production).
    get_redis()
    await get_arq_pool()
    try:
        await create_db_and_tables()
    except Exception as exc:  # pragma: no cover - dev convenience only
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
