# Worker and CLI

The Temporal worker (`python -m draftpilot.worker`, or `draftpilot worker`) runs every durable
workflow on one task queue, `TEMPORAL__TASK_QUEUE`. The web and MCP processes never import workflow
classes: they start workflows by type name through `draftpilot.core.temporal`. The room workflows
(`draftpilot.agents.room_workflows`) are documented in [Writers' room](agents.md).

Any edit to workflow code must pass the replay tests (`uv run pytest tests/test_temporal_replay.py`);
see [Extending the room](../extending-the-room.md).

## Workflows

Deterministic workflow classes. Their type names are the job names the web process starts
(`index_rag_document`, `delete_rag_document`, `reindex_project`, `refresh_story_twin`,
`purge_rag_project`), plus `execute_workflow`, which executes one persisted `WorkflowRun` and mirrors
its outcome into the row. New workflows are registered in `WORKFLOWS`.

::: draftpilot.worker.workflows

## Activities

The I/O behind every workflow. Long activities run inside `heartbeating()`, so a dead worker is
detected and cancellation is delivered. New activities are registered in `ACTIVITIES`.

::: draftpilot.worker.activities

## Job functions

The job logic itself: plain async functions the activities call, testable without Temporal.

::: draftpilot.worker.functions

## Worker entry point

::: draftpilot.worker.__main__

## Temporal client

The lazy Temporal client (`get_client` / `close_client`) and the start-by-name helpers:
`start_job`, `start_best_effort`, `start_run`, `cancel_run` and `signal_run`.

::: draftpilot.core.temporal

## The `draftpilot` command

`draftpilot serve`, `worker`, `migrate`, `mcp [--http]`, `rag` and `version`. Configuration comes
from the environment, exactly as in the Docker images.

::: draftpilot.cli
