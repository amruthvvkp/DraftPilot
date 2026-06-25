"""ARQ worker configuration.

Run with: ``arq draftpilot.worker.settings.WorkerSettings``
"""

from draftpilot.core import telemetry
from draftpilot.core.db import dispose_engine
from draftpilot.core.queue import redis_settings
from draftpilot.worker.functions import analyze_screenplay


async def startup(ctx: dict) -> None:
    """Configure worker telemetry when the ARQ worker starts."""
    telemetry.setup(worker=True)


async def shutdown(ctx: dict) -> None:
    """Dispose the database engine when the ARQ worker stops."""
    await dispose_engine()


class WorkerSettings:
    """ARQ worker configuration: tasks, Redis target, and lifecycle hooks."""

    functions = [analyze_screenplay]
    redis_settings = redis_settings()
    on_startup = startup
    on_shutdown = shutdown
