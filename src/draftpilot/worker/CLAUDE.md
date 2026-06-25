# Worker — ARQ background jobs

Runs as a separate process: `uv run arq draftpilot.worker.settings.WorkerSettings`.

- `settings.py` — `WorkerSettings` (functions list, `redis_settings()` from queue config, startup/
  shutdown hooks). Startup calls `telemetry.setup(worker=True)`; shutdown disposes the DB engine.
- `functions.py` — task coroutines `async def task(ctx, ...)`. Register new tasks in
  `WorkerSettings.functions`.

## Conventions

- Open DB sessions with `session_scope()`; cache results with `core.cache.cache_set` so the UI can read
  them (e.g. `analysis:{id}`).
- Wrap tasks in a `logfire.span(...)` and log completion with `logfire.info`.
- LLM calls go through PydanticAI behind `settings.llm` and MUST be optional — guard with
  `settings.llm.enabled` and a try/except so tasks succeed without a live provider.
