# DraftPilot

> This file mirrors `CLAUDE.md` for Codex / other agent runtimes. Keep the two in sync.

Open-source, agentic screenplay & story-development studio. A NiceGUI web app where writers build,
research, co-write, and evaluate screenplays alongside AI agents.

## Stack

- **UI**: NiceGUI (`from nicegui import app` IS the FastAPI app — one web process)
- **Agents**: PydanticAI (provider-agnostic: self-hosted or cloud LLMs)
- **Data**: Postgres via SQLModel + asyncpg; Alembic migrations
- **Cache / queue**: Redis; ARQ background worker (separate process)
- **Telemetry**: Logfire → OTLP → a **self-hosted Langfuse bundled in `compose.yml`** (part of the
  default stack). Logfire is the single logging + instrumentation backend. **On by default**: Langfuse
  auto-provisions a dev project whose keys match the default OTLP auth header, so traces flow on
  `docker compose up`. Override `OTEL__EXPORTER_OTLP_ENDPOINT` for an external Grafana LGTM, or set
  `OTEL__ENABLED=false`. Replace the `# CHANGEME` secrets before non-local use. See `.env.example`.
- **Docs**: Zensical (not MkDocs) — `zensical.toml`, sources in `docs/`
- **Tooling**: `uv` (Python pinned 3.13), `ruff`, `mypy`

## Layout

```
src/draftpilot/
  core/        config (pydantic-settings), telemetry, db/, cache/, queue/
  models/      SQLModel domain: Project → Screenplay → Scene
  crud/        thin async CRUD per model
  ui/          theme/ (design tokens + layout), components/ (reusable library), pages/, main.py
  worker/      ARQ WorkerSettings + task functions
  mcp/         FastMCP server
migrations/    Alembic (env.py reads settings sync DSN; SQLModel.metadata is the target)
```

## Run

```bash
# Full stack (Postgres, Redis, migrate, ui, worker, mcp + self-hosted Langfuse)
docker compose up --build         # UI :9000 · MCP :9001 · Langfuse :3300

# Local dev (needs local Postgres + Redis)
uv sync --group ui
uv run alembic upgrade head
uv run python -m draftpilot.ui.main
uv run arq draftpilot.worker.settings.WorkerSettings

# Debug stack (debugpy + live source mount + hot reload)
docker compose -f compose.yml -f compose.dev.yml up --build
# Attach VS Code: "Remote Attach (ui)" :5678 · "Remote Attach (worker)" :5679
```

## Conventions

- **Docstrings**: every module, class, function, method, and nested function gets a concise
  **one-line** Sphinx-style docstring (imperative mood). Interrogate enforces 100%
  (`[tool.interrogate]`, `fail-under = 100`) — `uv run interrogate src migrations` must pass.
- **Type hints**: annotate every function/method signature — all parameters and the return type
  (`-> None` when nothing is returned). Use modern syntax (`X | None`, `list[...]`, builtin
  generics). `uv run mypy src` must stay clean. Note: SQLModel `table=True` classes carry a
  `# type: ignore[call-arg]` (pydantic mypy-plugin false positive); `@computed_field` properties
  carry `# type: ignore[prop-decorator]`.
- Config: every settings group has an `env_prefix` (`POSTGRES__`, `REDIS__`, `QUEUE__`, `LLM__`,
  `UI__`, `OTEL__`). Nested env uses the `__` delimiter. Never read bare env names — they collide
  with system vars (e.g. `$USER`).
- Add UI building blocks to `ui/components/` and showcase them in `ui/components/design_system.py`.
- Pages are `content()` builders wrapped by `ui.theme.with_layout`; register routes in `ui/main.py`.
- After model changes: `uv run alembic revision --autogenerate -m "..."` then `upgrade head`.
- Branches follow the repo's GitHub-issue convention (e.g. `amruthvvkp/issueN`). Reference the issue
  in commits. (This repo is not on Jira; the global Jira branch rule does not apply here.)

Detailed local guidance lives in nested `CLAUDE.md` files under `src/draftpilot/{ui,worker,core}/`.
