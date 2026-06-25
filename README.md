# DraftPilot

Open-source, agentic screenplay & story-development studio. DraftPilot is a NiceGUI web application
where writers build, research, co-write, and evaluate screenplays alongside AI agents — from first
idea through pre-production planning.

## Stack

- **UI** — [NiceGUI](https://nicegui.io) (runs on its own FastAPI app)
- **Agents** — [PydanticAI](https://ai.pydantic.dev) (provider-agnostic: self-hosted or cloud LLMs)
- **Data** — Postgres + SQLModel (asyncpg), Alembic migrations
- **Cache / queue** — Redis + [ARQ](https://arq-docs.helpmanual.io) background worker
- **Telemetry** — [Logfire](https://logfire.pydantic.dev) → OTLP → your external collector (Grafana LGTM / Langfuse)
- **Docs** — [Zensical](https://zensical.org)
- **Tooling** — [uv](https://docs.astral.sh/uv), Ruff, mypy (Python 3.13)

## Quick start (Docker)

```bash
docker compose up --build
```

One command brings up the **whole stack**: Postgres, Redis, migrations, UI, ARQ worker, MCP server,
and a self-hosted **Langfuse** (web/worker/clickhouse/minio/postgres/redis).

- UI: <http://localhost:9000>
- MCP server: <http://localhost:9001>
- Langfuse: <http://localhost:3300> (dev login `dev@draftpilot.local` / `draftpilot-dev`)

Published host ports are env-configurable (defaults shown) to avoid clashing with a local
Postgres/Redis or a shared stack: `DRAFTPILOT_POSTGRES_PORT` (55432), `DRAFTPILOT_REDIS_PORT` (56379),
`DRAFTPILOT_UI_PORT` (9000), `DRAFTPILOT_MCP_PORT` (9001), `DRAFTPILOT_LANGFUSE_PORT` (3300). See
`.env.example`.

### Telemetry

**On by default.** Logfire ships OTLP traces/metrics/logs to the in-stack Langfuse, which
auto-provisions a dev project on first boot whose keys match the default auth header — so traces
flow with no extra setup (give Langfuse ~1 min to finish migrations after the first `up`). Set
`OTEL__ENABLED=false` to disable, or override `OTEL__EXPORTER_OTLP_ENDPOINT` to point at an external
Grafana LGTM / collector instead. **Replace the `# CHANGEME` secrets in `compose.yml` before any
non-local use.** See `.env.example`.

## Local development

Requires a local Postgres + Redis (or run `docker compose up postgres redis`).

```bash
uv sync --group ui
uv run alembic upgrade head
uv run python -m draftpilot.ui.main                    # UI on :8000
uv run arq draftpilot.worker.settings.WorkerSettings   # worker (separate shell)
```

Connection settings are overridable via prefixed environment variables — e.g. `POSTGRES__HOST`,
`REDIS__HOST`, `QUEUE__DB`, `UI__PORT`, `OTEL__ENABLED`, `LLM__*`.

## Try the vertical slice

Open the UI, create a **Project**, add a **Screenplay**, write a few **Scenes**, then click
**Run analysis**. The ARQ worker computes structural metrics (and, if an LLM provider is configured,
a short qualitative note), caches the result in Redis, and the UI displays it.

## Documentation

```bash
uv run zensical serve     # live docs
```

See `docs/` and `zensical.toml`.

## License

MIT
