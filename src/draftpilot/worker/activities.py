"""Temporal activities: the I/O behind every workflow, wrapping the job logic in ``functions.py``."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from temporalio import activity

from draftpilot.agents import workflow_runner
from draftpilot.agents.workflows import RoomRunInput
from draftpilot.worker import functions

HEARTBEAT_SECONDS = 10


@asynccontextmanager
async def heartbeating() -> AsyncIterator[None]:
    """Heartbeat in the background so Temporal can tell a slow activity from a dead worker and deliver cancels."""

    async def beat() -> None:
        """Send a heartbeat every few seconds until cancelled."""
        while True:
            activity.heartbeat()
            await asyncio.sleep(HEARTBEAT_SECONDS)

    task = asyncio.create_task(beat())
    try:
        yield
    finally:
        task.cancel()


@activity.defn
async def index_rag_document(document: dict[str, Any]) -> dict[str, str]:
    """Index one approved document in the RAG service."""
    return await functions.index_rag_document(document)


@activity.defn
async def delete_rag_document(document: dict[str, Any]) -> dict[str, str]:
    """Delete one document from the RAG service."""
    return await functions.delete_rag_document(document)


@activity.defn
async def reindex_project(project_id: int) -> dict[str, object]:
    """Re-send every retrievable document of a project to the RAG service."""
    async with heartbeating():
        return await functions.reindex_project(project_id)


@activity.defn
async def refresh_story_twin(project_id: int) -> dict[str, int]:
    """Re-derive the Story twin from the working draft."""
    async with heartbeating():
        return await functions.refresh_story_twin(project_id)


@activity.defn
async def purge_rag_project(project_id: int) -> dict[str, object]:
    """Remove a deleted project's documents from the RAG service."""
    return await functions.purge_rag_project(project_id)


@activity.defn
async def begin_run(run_id: int, workflow_id: str) -> dict[str, object]:
    """Mark a persisted run as running and describe how to execute it."""
    return await functions.begin_run(run_id, workflow_id)


@activity.defn
async def run_job(run_id: int) -> dict[str, Any]:
    """Execute one attempt of a persisted run (Temporal retries it up to the run's ``max_attempts``)."""
    async with heartbeating():
        return await functions.run_job(run_id, activity.info().attempt)


@activity.defn
async def finish_run(run_id: int, status: str, result: dict[str, Any] | None, error: str | None) -> str:
    """Record a run's terminal state in its Postgres copy and return the status it ended in."""
    return await functions.finish_run(run_id, status, result, error)


@activity.defn
async def prepare_room_run(run_id: int) -> tuple[str, RoomRunInput]:
    """Resolve a room run's workflow, model (including LM Studio ``auto``) and room context."""
    return await workflow_runner.prepare_room_run(run_id)


@activity.defn
async def room_checks(result: dict[str, Any]) -> dict[str, Any]:
    """Score a finished room workflow with the online checks."""
    return workflow_runner.with_checks(result)


ACTIVITIES: list[Callable[..., Any]] = [
    index_rag_document,
    delete_rag_document,
    reindex_project,
    refresh_story_twin,
    purge_rag_project,
    begin_run,
    run_job,
    finish_run,
    prepare_room_run,
    room_checks,
]


def all_activities() -> list[Callable[..., Any]]:
    """Return the job activities, the room workflows' database steps, and the room agents' model and tool calls."""
    from draftpilot.agents.runtime import room_agent_activities
    from draftpilot.agents.workflows import ROOM_ACTIVITIES

    return [*ACTIVITIES, *ROOM_ACTIVITIES, *room_agent_activities()]
