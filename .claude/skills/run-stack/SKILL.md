---
name: run-stack
description: Bring up or run the DraftPilot stack (FastAPI web + React studio, ARQ worker, MCP server, RAG service, Postgres, Redis, Langfuse). Use when asked to run, start, or boot the app or any of its services, locally or via Docker.
---

# Run the DraftPilot stack

## Docker (full stack)

```bash
docker compose up --build        # all services
docker compose up postgres redis # just the backing stores
docker compose run --rm migrate  # apply migrations once (alembic upgrade head)
```

Endpoints: studio + API (`ui` service) `http://localhost:9000`, MCP (FastMCP HTTP)
`http://localhost:9001`, RAG `http://localhost:9010`, Langfuse `http://localhost:3300`.

`docker compose up` brings up the whole stack including a self-hosted **Langfuse**
(web/worker/clickhouse/minio/postgres/redis). Telemetry is **ON by default** and ships to that
Langfuse, which auto-provisions a dev project whose keys match the default OTLP auth header — traces
flow with no setup (allow ~1 min for Langfuse migrations on first boot). Disable with
`OTEL__ENABLED=false`; point at external Grafana LGTM via `OTEL__EXPORTER_OTLP_ENDPOINT`. Replace the
`# CHANGEME` secrets before non-local use. See `.env.example`.

Debug overlay: `docker compose -f compose.yml -f compose.dev.yml up --build` mounts `./src` into
ui/worker/mcp and `./frontend/dist` into ui, sets `WEB__RELOAD=true`, and exposes debugpy
(ui :5678, worker :5679). Rebuild the frontend locally to update the served bundle.

## Local (no Docker)

Requires a local Postgres + Redis (or `docker compose up postgres redis`).

```bash
uv sync --all-groups                                   # or --group web for just the app
uv run alembic upgrade head
npm --prefix frontend install && npm --prefix frontend run build   # React build -> frontend/dist
uv run python -m draftpilot.api                        # API + studio on :8000
npm --prefix frontend run dev                          # optional Vite HMR on :5173 (proxies /api)
uv run arq draftpilot.worker.settings.WorkerSettings   # worker (separate shell)
uv run python -m draftpilot.mcp                        # MCP over stdio
```

Override settings with prefixed env vars, e.g. `POSTGRES__HOST`, `REDIS__HOST`, `QUEUE__DB`,
`WEB__PORT`, `WEB__RELOAD`, `API__TOKEN`, `OTEL__ENABLED`.

Published host ports are env-configurable (defaults in parentheses): `DRAFTPILOT_POSTGRES_PORT`
(55432), `DRAFTPILOT_REDIS_PORT` (56379), `DRAFTPILOT_UI_PORT` (9000), `DRAFTPILOT_MCP_PORT` (9001),
`DRAFTPILOT_RAG_PORT` (9010), `DRAFTPILOT_LANGFUSE_PORT` (3300), `DRAFTPILOT_UI_DEBUGPY_PORT` (5678),
`DRAFTPILOT_WORKER_DEBUGPY_PORT` (5679). Set them in `.env`. Container-internal ports never change.

## Tests

```bash
uv run pytest                        # Tier 0: deterministic suite (default)
uv run pytest -m lmstudio            # Tier 1: needs a local LM Studio server
uv run playwright install chromium   # once
uv run pytest tests/e2e              # browser journeys against :9000
docker compose --profile test run --rm e2e   # same, in the pinned Playwright container
```

## Verify

Open `http://localhost:9000` → create a Project in the wizard → open its workspace. `GET /health`
should respond, and agent traces appear in Langfuse (`:3300`).
