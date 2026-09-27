---
name: run-stack
description: Bring up or run the DraftPilot stack (FastAPI web + React studio, Temporal worker, MCP server, RAG service, Postgres, Redis, Temporal). Use when asked to run, start, or boot the app or any of its services, locally or via Docker.
---

# Run the DraftPilot stack

## Docker (full stack)

```bash
docker compose up --build        # all services
docker compose up postgres redis # just the backing stores
docker compose run --rm migrate  # apply migrations once (alembic upgrade head)
```

Endpoints: studio + API (`ui` service) `http://localhost:9000`, MCP (FastMCP HTTP)
`http://localhost:9001`, RAG `http://localhost:9010`, Temporal UI `http://localhost:8233`
(workflow histories for every run and background job).

Telemetry is **off by default**. `docker compose --profile observability up` adds Grafana
`otel-lgtm` (Grafana `http://localhost:3300`, OTLP :4318); set `OTEL__ENABLED=true` to export to it,
or point `OTEL__EXPORTER_OTLP_ENDPOINT` at another collector. See `.env.example`.

New settings reach containers only after a rebuild: run `docker compose build` before `up -d`.

Debug overlay: `docker compose -f compose.yml -f compose.dev.yml up --build` mounts `./src` into
ui/worker/mcp and `./frontend/dist` into ui, sets `WEB__RELOAD=true`, and exposes debugpy
(ui :5678, worker :5679). Rebuild the frontend locally to update the served bundle.

## Local (no Docker)

Requires a local Postgres + Redis + Temporal (`docker compose up postgres redis temporal`, or
`temporal server start-dev` from the Temporal CLI).

```bash
uv sync --all-groups                                   # or --group web for just the app
uv run alembic upgrade head
npm --prefix frontend install && npm --prefix frontend run build   # React build -> frontend/dist
uv run python -m draftpilot.api                        # API + studio on :8000
npm --prefix frontend run dev                          # optional Vite HMR on :5173 (proxies /api)
uv run python -m draftpilot.worker                     # Temporal worker (separate shell)
uv run python -m draftpilot.mcp                        # MCP over stdio
```

Override settings with prefixed env vars, e.g. `POSTGRES__HOST`, `REDIS__HOST`, `TEMPORAL__HOST`,
`WEB__PORT`, `WEB__RELOAD`, `API__TOKEN`, `OTEL__ENABLED`.

Published host ports are env-configurable (defaults in parentheses): `DRAFTPILOT_POSTGRES_PORT`
(55432), `DRAFTPILOT_REDIS_PORT` (56379), `DRAFTPILOT_UI_PORT` (9000), `DRAFTPILOT_MCP_PORT` (9001),
`DRAFTPILOT_RAG_PORT` (9010), `DRAFTPILOT_TEMPORAL_PORT` (7233), `DRAFTPILOT_TEMPORAL_UI_PORT` (8233),
`DRAFTPILOT_GRAFANA_PORT` (3300), `DRAFTPILOT_OTLP_HTTP_PORT` (4318), `DRAFTPILOT_UI_DEBUGPY_PORT` (5678),
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
should respond, and background work shows up as workflows in the Temporal UI (`:8233`).
