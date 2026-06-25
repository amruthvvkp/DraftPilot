---
name: run-stack
description: Bring up or run the DraftPilot stack (NiceGUI UI, ARQ worker, Postgres, Redis, MCP). Use when asked to run, start, or boot the app or any of its services, locally or via Docker.
---

# Run the DraftPilot stack

## Docker (full stack)

```bash
docker compose up --build        # all services
docker compose up postgres redis # just the backing stores
docker compose run --rm migrate  # apply migrations once
```

Endpoints: UI `http://localhost:9000`, MCP `http://localhost:9001`, Langfuse `http://localhost:3300`.

`docker compose up` brings up the whole stack including a self-hosted **Langfuse**
(web/worker/clickhouse/minio/postgres/redis). Telemetry is **ON by default** and ships to that
Langfuse, which auto-provisions a dev project whose keys match the default OTLP auth header — traces
flow with no setup (allow ~1 min for Langfuse migrations on first boot). Disable with
`OTEL__ENABLED=false`; point at external Grafana LGTM via `OTEL__EXPORTER_OTLP_ENDPOINT`. Replace the
`# CHANGEME` secrets before non-local use. See `.env.example`.

## Local (no Docker)

Requires a local Postgres + Redis (or `docker compose up postgres redis`).

```bash
uv sync --group ui
uv run alembic upgrade head
uv run python -m draftpilot.ui.main                              # UI
uv run arq draftpilot.worker.settings.WorkerSettings            # worker (separate shell)
```

Override connection settings with prefixed env vars, e.g. `POSTGRES__HOST`, `REDIS__HOST`,
`QUEUE__DB`, `UI__PORT`, `OTEL__ENABLED`.

Published host ports are env-configurable to avoid clashes with a local Postgres/Redis or a shared
stack (defaults in parentheses): `DRAFTPILOT_POSTGRES_PORT` (55432), `DRAFTPILOT_REDIS_PORT` (56379),
`DRAFTPILOT_UI_PORT` (9000), `DRAFTPILOT_MCP_PORT` (9001), `DRAFTPILOT_UI_DEBUGPY_PORT` (5678),
`DRAFTPILOT_WORKER_DEBUGPY_PORT` (5679). Set them in `.env`. Container-internal ports never change.

## Verify the vertical slice

Open the UI → create a Project → add a Screenplay → add Scenes → click **Run analysis**. The worker
processes the job; click **Refresh result** to see cached metrics. The PydanticAI agent's traces
appear in Langfuse (`:3300`) since telemetry is on by default.
