"""Temporal workflows: durable background jobs and the executor of persisted WorkflowRuns.

Workflow code must be deterministic: it only schedules activities (``worker/activities.py``) and
decides from their results. Workflow type names match the job names the web process starts by
(see ``core/temporal.py``). Any edit here must pass the replay tests over
``tests/temporal_histories/``.
"""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ChildWorkflowError

with workflow.unsafe.imports_passed_through():
    from draftpilot.agents.workflow_runner import ROOM_WORKFLOW_KIND
    from draftpilot.worker import activities

JOB_RETRY = RetryPolicy(initial_interval=timedelta(seconds=2), maximum_attempts=5)
JOB_TIMEOUT = timedelta(minutes=10)
BOOKKEEPING_TIMEOUT = timedelta(seconds=30)
# A run's attempt may be a long local-model room workflow; heartbeats detect a dead worker sooner.
RUN_ATTEMPT_TIMEOUT = timedelta(hours=6)
RUN_HEARTBEAT_TIMEOUT = timedelta(minutes=2)
# Preparing a room run resolves the model (LM Studio ``auto`` lists models); a ValueError is final.
PREPARE_RETRY = RetryPolicy(maximum_attempts=3, non_retryable_error_types=["ValueError", "RuntimeError"])


def root_message(error: BaseException) -> str:
    """Return the innermost failure message a Temporal activity or child-workflow error wraps."""
    message = str(error)
    current: BaseException | None = error
    while current is not None:
        if str(current):
            message = getattr(current, "message", None) or str(current)
        current = getattr(current, "cause", None)
    return message


@workflow.defn(name="index_rag_document")
class IndexRagDocument:
    """Index one approved document in the RAG service."""

    @workflow.run
    async def run(self, document: dict[str, Any]) -> dict[str, str]:
        """Run the index activity with retries."""
        return await workflow.execute_activity(
            activities.index_rag_document, document, start_to_close_timeout=JOB_TIMEOUT, retry_policy=JOB_RETRY
        )


@workflow.defn(name="delete_rag_document")
class DeleteRagDocument:
    """Delete one document from the RAG service."""

    @workflow.run
    async def run(self, document: dict[str, Any]) -> dict[str, str]:
        """Run the delete activity with retries."""
        return await workflow.execute_activity(
            activities.delete_rag_document, document, start_to_close_timeout=JOB_TIMEOUT, retry_policy=JOB_RETRY
        )


@workflow.defn(name="reindex_project")
class ReindexProject:
    """Re-send a project's retrievable documents to the RAG service, then refresh its Story twin."""

    @workflow.run
    async def run(self, project_id: int) -> dict[str, object]:
        """Run the reindex activity with retries."""
        return await workflow.execute_activity(
            activities.reindex_project,
            project_id,
            start_to_close_timeout=timedelta(hours=1),
            heartbeat_timeout=RUN_HEARTBEAT_TIMEOUT,
            retry_policy=JOB_RETRY,
        )


@workflow.defn(name="refresh_story_twin")
class RefreshStoryTwin:
    """Run the Twin Keeper over a project's working draft."""

    @workflow.run
    async def run(self, project_id: int) -> dict[str, int]:
        """Run the refresh activity with retries."""
        return await workflow.execute_activity(
            activities.refresh_story_twin,
            project_id,
            start_to_close_timeout=JOB_TIMEOUT,
            heartbeat_timeout=RUN_HEARTBEAT_TIMEOUT,
            retry_policy=JOB_RETRY,
        )


@workflow.defn(name="purge_rag_project")
class PurgeRagProject:
    """Remove a deleted project's documents from the RAG service."""

    @workflow.run
    async def run(self, project_id: int) -> dict[str, object]:
        """Run the purge activity with retries."""
        return await workflow.execute_activity(
            activities.purge_rag_project, project_id, start_to_close_timeout=JOB_TIMEOUT, retry_policy=JOB_RETRY
        )


@workflow.defn(name="execute_workflow")
class ExecuteRun:
    """Execute one persisted WorkflowRun and mirror its outcome into the Postgres row.

    A room run executes its room workflow as a child workflow. Every other kind executes as one
    activity that Temporal retries up to the run's ``max_attempts``.
    """

    @workflow.run
    async def run(self, run_id: int) -> dict[str, Any]:
        """Begin the run, execute it, and record the terminal state."""
        plan = await workflow.execute_activity(
            activities.begin_run, args=[run_id, workflow.info().workflow_id], start_to_close_timeout=BOOKKEEPING_TIMEOUT
        )
        if "skip" in plan:
            return {"status": plan["skip"]}
        try:
            if plan["kind"] == ROOM_WORKFLOW_KIND:
                result = await self.room(run_id)
            else:
                result = await workflow.execute_activity(
                    activities.run_job,
                    run_id,
                    start_to_close_timeout=RUN_ATTEMPT_TIMEOUT,
                    heartbeat_timeout=RUN_HEARTBEAT_TIMEOUT,
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=5), maximum_attempts=int(str(plan["max_attempts"]))
                    ),
                )
        except (ActivityError, ChildWorkflowError) as exc:
            error = root_message(exc)
            status = await self.finish(run_id, "failed", None, error)
            return {"status": "failed", "error": error} if status == "failed" else {"status": status}
        status = await self.finish(run_id, "succeeded", result, None)
        return result if status == "succeeded" else {"status": status}

    async def room(self, run_id: int) -> dict[str, Any]:
        """Prepare the room run, execute its room workflow as a child, and score the result."""
        type_name, room_input = await workflow.execute_activity(
            activities.prepare_room_run, run_id, start_to_close_timeout=timedelta(minutes=2), retry_policy=PREPARE_RETRY
        )
        result: dict[str, Any] = await workflow.execute_child_workflow(
            type_name, room_input, id=f"{workflow.info().workflow_id}-room", result_type=dict
        )
        return await workflow.execute_activity(activities.room_checks, result, start_to_close_timeout=BOOKKEEPING_TIMEOUT)

    async def finish(self, run_id: int, status: str, result: dict[str, Any] | None, error: str | None) -> str:
        """Record the terminal state and return the status the run ended in (a cancel may have won)."""
        final: str = await workflow.execute_activity(
            activities.finish_run, args=[run_id, status, result, error], start_to_close_timeout=BOOKKEEPING_TIMEOUT
        )
        return final


WORKFLOWS: list[type] = [IndexRagDocument, DeleteRagDocument, ReindexProject, RefreshStoryTwin, PurgeRagProject, ExecuteRun]


def all_workflows() -> list[type]:
    """Return the job workflows, the eight room workflows and the chat turn."""
    from draftpilot.agents.room_workflows import ROOM_WORKFLOW_CLASSES, RoomChat

    return [*WORKFLOWS, *ROOM_WORKFLOW_CLASSES, RoomChat]
