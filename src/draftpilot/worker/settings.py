"""ARQ worker configuration.

Run with: ``arq draftpilot.worker.settings.WorkerSettings``
"""

from typing import Any, ClassVar

from draftpilot.core import telemetry
from draftpilot.core.db import dispose_engine, session_scope
from draftpilot.core.queue import close_arq_pool, get_arq_pool, redis_settings
from draftpilot.crud import workflow_runs as workflow_runs_crud
from draftpilot.worker.functions import (
    analyze_screenplay,
    delete_rag_document,
    execute_workflow,
    index_rag_document,
    purge_rag_project,
    push_langfuse_scores,
    refresh_story_twin,
    reindex_project,
)


async def startup(ctx: dict) -> None:
    """Configure telemetry and recover runs interrupted by a worker exit."""
    telemetry.setup(worker=True)
    async with session_scope() as session:
        interrupted = await workflow_runs_crud.list_interrupted(session)
        for run in interrupted:
            run.status = "queued"
            run.error = "Requeued after worker restart"
            session.add(run)
        if interrupted:
            await session.commit()
    if interrupted:
        pool = await get_arq_pool()
        for run in interrupted:
            if run.id is not None:
                await pool.enqueue_job("execute_workflow", run.id)


async def shutdown(ctx: dict) -> None:
    """Close the enqueue pool and dispose the database engine."""
    await close_arq_pool()
    await dispose_engine()


class WorkerSettings:
    """ARQ worker configuration: tasks, Redis target, and lifecycle hooks."""

    functions: ClassVar[list[Any]] = [analyze_screenplay, delete_rag_document, execute_workflow, index_rag_document, purge_rag_project, push_langfuse_scores, refresh_story_twin, reindex_project]
    redis_settings = redis_settings()
    on_startup = startup
    on_shutdown = shutdown
