"""Temporal client for starting durable workflows from the web and MCP processes.

The worker (``python -m draftpilot.worker``) runs the workflows. Callers start them by type name
(the old job names: ``index_rag_document``, ``reindex_project``, ``execute_workflow``, ...), so no
web-side module has to import workflow code.
"""

import uuid
from datetime import timedelta
from typing import Any

import logfire
from temporalio.client import Client, Plugin
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from draftpilot.core.config import settings

RUN_WORKFLOW = "execute_workflow"

_client: Client | None = None


def plugins() -> list[Plugin]:
    """Return the client plugins: Pydantic AI payloads always, Logfire tracing when telemetry is on."""
    from pydantic_ai.durable_exec.temporal import LogfirePlugin, PydanticAIPlugin

    installed: list[Plugin] = [PydanticAIPlugin()]
    if settings.otel.enabled:
        installed.append(LogfirePlugin(lambda: logfire.DEFAULT_LOGFIRE_INSTANCE, metrics=False))
    return installed


async def connect() -> Client:
    """Open a new client to the configured Temporal namespace."""
    return await Client.connect(settings.temporal.host, namespace=settings.temporal.namespace, plugins=plugins())


async def get_client() -> Client:
    """Return the shared client, connecting on first use."""
    global _client
    if _client is None:
        _client = await connect()
    return _client


async def close_client() -> None:
    """Forget the shared client on shutdown (its connection closes with the process)."""
    global _client
    _client = None


def run_workflow_id(run_id: int) -> str:
    """Return the Temporal workflow id of a persisted WorkflowRun."""
    return f"run-{run_id}"


async def start_job(
    workflow: str,
    *args: Any,
    id: str | None = None,
    start_delay: timedelta | None = None,
    collapse: bool = False,
) -> str:
    """Start a workflow by type name and return its id.

    ``collapse`` joins an already-running workflow with the same id instead of failing, so a burst
    of requests (with ``start_delay`` as the debounce window) becomes one run.
    """
    workflow_id = id or f"{workflow}-{uuid.uuid4().hex}"
    await (await get_client()).start_workflow(
        workflow,
        args=list(args),
        id=workflow_id,
        task_queue=settings.temporal.task_queue,
        start_delay=start_delay,
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING if collapse else WorkflowIDConflictPolicy.FAIL,
    )
    return workflow_id


async def start_best_effort(workflow: str, *args: Any, description: str, **options: Any) -> bool:
    """Start an optional workflow, logging instead of failing when Temporal is unreachable."""
    try:
        await start_job(workflow, *args, **options)
    except Exception as exc:  # noqa: BLE001 - Temporal availability varies by deployment
        logfire.warning(description + " skipped: {exc}", exc=str(exc))
        return False
    return True


async def start_run(run_id: int | None) -> str:
    """Start the durable execution of a persisted WorkflowRun and return the Temporal workflow id."""
    if run_id is None:
        raise ValueError("Only a persisted run can be started")
    return await start_job(RUN_WORKFLOW, run_id, id=run_workflow_id(run_id), collapse=True)


async def cancel_run(run_id: int | None) -> None:
    """Ask Temporal to cancel a run's workflow; a run that already finished is left alone."""
    if run_id is None:
        return
    try:
        await (await get_client()).get_workflow_handle(run_workflow_id(run_id)).cancel()
    except Exception as exc:  # noqa: BLE001 - the Postgres status is authoritative for the UI
        logfire.warning("Workflow cancel for run {run_id} skipped: {exc}", run_id=run_id, exc=str(exc))
