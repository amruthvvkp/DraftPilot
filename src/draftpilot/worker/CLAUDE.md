# Worker — Temporal workflows and activities

Runs as a separate process: `uv run python -m draftpilot.worker` (one Temporal worker on
`TEMPORAL__TASK_QUEUE`). The web and MCP processes start workflows by type name through
`core/temporal.py` (`start_job`, `start_best_effort`, `start_run`).

- `workflows.py` — `@workflow.defn` classes. Type names are the job names (`index_rag_document`,
  `reindex_project`, `refresh_story_twin`, `purge_rag_project`, `delete_rag_document`) plus
  `execute_workflow`, which executes one persisted `WorkflowRun` with the run's `max_attempts` as its
  retry policy and mirrors the outcome into the row. Register new workflows in `WORKFLOWS`.
- `activities.py` — `@activity.defn` wrappers (all I/O). Long ones run inside `heartbeating()` so a
  dead worker is detected and cancels are delivered. Register new ones in `ACTIVITIES`.
- `functions.py` — the job logic itself (plain async functions, testable without Temporal).

## Conventions

- Workflow code is deterministic: no I/O, clocks or randomness — only activities, timers and
  `workflow.*` APIs. Import activity modules inside `workflow.unsafe.imports_passed_through()`.
- **Any workflow edit must pass the replay tests** over `tests/temporal_histories/`.
- Open DB sessions with `session_scope()` inside activities; cache results with `core.cache.cache_set`.
- Wrap job logic in a `logfire.span(...)`.
- LLM calls go through PydanticAI behind `settings.llm` and MUST be optional — guard with
  `settings.llm.enabled` and a try/except so jobs succeed without a live provider.
