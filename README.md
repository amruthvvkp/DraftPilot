# DraftPilot

Open-source, agent-first screenplay & story-development studio. DraftPilot is a local-first
writers' room: you build, research, co-write, and evaluate screenplays alongside AI agents that
propose changes you approve — from first idea through pre-production planning.

## Stack

- **Studio** — React 19 + Vite + TypeScript SPA (`frontend/`), served by the web process
- **API** — [FastAPI](https://fastapi.tiangolo.com) app factory (`draftpilot.api.app:create_app`), routes under `/api/v1`, optional `API__TOKEN`
- **MCP** — [FastMCP](https://gofastmcp.com) 4 server (HTTP or stdio) with writer-approved tool calls
- **Agents** — [PydanticAI](https://ai.pydantic.dev) (provider-agnostic: self-hosted or cloud LLMs)
- **Worker** — [ARQ](https://arq-docs.helpmanual.io) background jobs on Redis
- **RAG** — standalone retrieval service (`draftpilot.rag_service`), project-scoped search
- **Data** — Postgres + SQLModel (asyncpg), Alembic migrations; Redis cache/queue
- **Telemetry** — [Logfire](https://logfire.pydantic.dev) → OTLP → self-hosted Langfuse (bundled)
- **Docs / tooling** — [Zensical](https://zensical.org), [uv](https://docs.astral.sh/uv), Ruff, mypy (Python 3.13)

## Quick start (Docker)

```bash
docker compose up --build
```

One command brings up the **whole stack**: Postgres, Redis, migrations, the web process (API +
studio), ARQ worker, MCP server, RAG service, and a self-hosted **Langfuse**.

- Studio + API: <http://localhost:9000>
- MCP server (HTTP): <http://localhost:9001>
- RAG service: <http://localhost:9010>
- Langfuse: <http://localhost:3300> (dev login `dev@draftpilot.local` / `draftpilot-dev`)

Host ports are env-configurable (`DRAFTPILOT_UI_PORT`, `DRAFTPILOT_MCP_PORT`, `DRAFTPILOT_RAG_PORT`,
`DRAFTPILOT_POSTGRES_PORT`, `DRAFTPILOT_REDIS_PORT`, `DRAFTPILOT_LANGFUSE_PORT`); see `.env.example`.

Debug stack (live source mount, hot reload, debugpy on ui :5678 / worker :5679):

```bash
docker compose -f compose.yml -f compose.dev.yml up --build
```

### Telemetry

**On by default.** Logfire ships OTLP traces/metrics/logs to the in-stack Langfuse, which
auto-provisions a dev project whose keys match the default auth header (allow ~1 min for Langfuse
migrations on first boot). Set `OTEL__ENABLED=false` to disable, or override
`OTEL__EXPORTER_OTLP_ENDPOINT` for an external collector. **Replace the `# CHANGEME` secrets in
`compose.yml` before any non-local use.**

## Local development

Requires a local Postgres + Redis (or `docker compose up postgres redis`) and Node.js.

```bash
uv sync --all-groups                                   # or --group web for just the app
uv run alembic upgrade head
npm --prefix frontend install
npm --prefix frontend run build                        # typecheck + build -> frontend/dist
uv run python -m draftpilot.api                        # API + studio on :8000
npm --prefix frontend run dev                          # optional Vite HMR on :5173 (proxies /api)
uv run arq draftpilot.worker.settings.WorkerSettings   # worker (separate shell)
uv run python -m draftpilot.mcp                        # MCP server over stdio
```

Settings use prefixed environment variables with a `__` delimiter — e.g. `POSTGRES__HOST`,
`REDIS__HOST`, `WEB__PORT`, `API__TOKEN`, `LLM__*`, `MCP__*`, `RAG__*`, `OTEL__ENABLED`. Provider
credentials are encrypted with a Fernet key in `SECRETS__MASTER_KEY`.

## Testing

| Tier | Command | Needs |
| --- | --- | --- |
| 0 — deterministic | `uv run pytest` | nothing (default) |
| 1 — local model | `uv run pytest -m lmstudio` | LM Studio local server |
| Browser | `uv run pytest tests/e2e` | stack on :9000, `uv run playwright install chromium` |
| Browser (container) | `docker compose --profile test run --rm e2e` | Docker |

Browser journeys mock the API with Playwright routes and never depend on live database state.
Quality gates: `uv run ruff check src tests`, `uv run mypy src`, `uv run interrogate src migrations`,
`npm --prefix frontend run build`. See `docs/testing.md`.

## Documentation

```bash
uv run zensical serve     # live docs
```

- Roadmap: [`docs/roadmap.md`](docs/roadmap.md)
- v1 gap analysis: [`docs/dev/v1-gap-analysis.md`](docs/dev/v1-gap-analysis.md)
- MCP capability boundary: [`docs/mcp.md`](docs/mcp.md)
- Credits: [`docs/references.md`](docs/references.md)

## License

MIT
