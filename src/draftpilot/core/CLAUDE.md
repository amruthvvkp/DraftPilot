# Core — config, telemetry, infra

- `config.py` — `settings` singleton. Each group is a `BaseSettings` with its own `env_prefix`
  (`POSTGRES__`, `REDIS__`, `TEMPORAL__`, `LLM__`, `WEB__`, `API__`, `MCP__`, `EVAL__`, `OTEL__`, ...). Postgres exposes `async_dsn`
  (asyncpg, app engine) and `sync_dsn` (psycopg, Alembic). Secrets use `SecretStr`.
- `telemetry.py` — `setup(web|mcp|worker=...)`, `instrument_app(app)`, guarded `instrument_mcp()`. Configures Logfire (no cloud; OTLP export only) and
  instruments the libraries used by that process. No-op when `OTEL__ENABLED` is false.
- `db/database.py` — async engine + `async_session_factory`; `session_scope()` context manager,
  `async_get_db()` dependency. Alembic owns the schema; nothing creates tables at startup.
- `cache/redis.py` — shared async Redis client + JSON `cache_get`/`cache_set`.
- `temporal.py` — lazy Temporal `Client` (`get_client`/`close_client`) and start-by-name helpers:
  `start_job`, `start_best_effort`, `start_run(run_id)`, `cancel_run`. Workflows live in `worker/`.

## Conventions

- New settings group → new `BaseSettings` subclass with an `env_prefix`, added as a field on `Settings`.
- New infra resource that holds a connection → expose a lazy getter + a `close_*` coroutine, and wire
  both into the web lifespan in `api/app.py` and the worker startup/shutdown in `worker/__main__.py`.
