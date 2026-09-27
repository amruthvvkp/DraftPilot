# DraftPilot

Open-source, agentic screenplay & story-development studio. A local-first React/Vite web app where
writers build, research, co-write, and evaluate screenplays alongside AI agents.

## Stack

- **Web**: FastAPI app factory (`api/app.py:create_app`, `python -m draftpilot.api`) serving `/api/v1`
  and the React 19 + Vite + TypeScript studio build (`frontend/dist`)
- **Agents**: PydanticAI (provider-agnostic). **All LLM-backed tests/evals run on local LM Studio**
- **MCP**: FastMCP 4 / MCP SDK 2 — the one tool surface for in-app and external agents
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
  api/         app.py (create_app), __main__.py (uvicorn), routers under /api/v1, auth
  core/        config (pydantic-settings), telemetry, db/, cache/, queue/, screenplay/, domain services
  models/      SQLModel domain: Project → Screenplay → Act → Scene → Block (+ story, agents, MCP access)
  crud/        thin async CRUD per model
  agents/      writers' room: role specs (specs/*.yaml), runtime, room workflows (pydantic_graph)
  evals/       pydantic_evals suites on LM Studio (`python -m draftpilot.evals`) + online checks
  worker/      ARQ WorkerSettings + task functions
  mcp/         FastMCP server (HTTP + stdio)
frontend/      React/Vite studio (src/, public/ assets; build → dist/)
migrations/    Alembic (env.py reads settings sync DSN; SQLModel.metadata is the target)
```

## Run

```bash
# Full stack (Postgres, Redis, migrate, ui(web), worker, mcp, rag + self-hosted Langfuse)
docker compose up --build         # Studio :9000 · MCP :9001 · RAG :9010 · Langfuse :3300

# Local dev (needs local Postgres + Redis)
uv sync --all-groups
uv run alembic upgrade head
uv run python -m draftpilot.api       # API + built studio on :8000
npm --prefix frontend run dev         # React studio with Vite hot reload
uv run arq draftpilot.worker.settings.WorkerSettings

# Tests: Tier 0 (CI) · browser e2e (stack on :9000) · Tier 1 local LM Studio
uv run pytest tests --ignore=tests/e2e && uv run pytest tests/e2e && uv run pytest -m lmstudio

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
  `WEB__`, `API__`, `MCP__`, `RAG__`, `EVAL__`, `OTEL__`, ...). Nested env uses the `__` delimiter.
  Never read bare env names — they collide with system vars (e.g. `$USER`).
- React pages and components live in `frontend/src`; register API routers in `api/__init__.py`
  (the `protected` router, so `API__TOKEN` applies). See `frontend/CLAUDE.md`.
- Agents never write silently: they create proposals the writer approves; MCP approval-required calls
  need a writer-decided `approval_id` (see `docs/mcp.md`).
- Any change to an agent, prompt, spec or tool must run that agent's evals on LM Studio
  (`uv run python -m draftpilot.evals <suite>`; baselines in `evals/baselines/`, see `docs/evals.md`).
- After model changes: `uv run alembic revision --autogenerate -m "..."`, then **review it** — the
  existing schema has known TEXT/AutoString drift that autogenerate re-detects; keep only your
  change (hand-write it if needed), check `downgrade`, then `upgrade head`.
- Branches follow the repo's GitHub-issue convention (e.g. `amruthvvkp/issueN`). Reference the issue
  in commits. (This repo is not on Jira; the global Jira branch rule does not apply here.)
- **Roadmap**: `docs/roadmap.md`; v1 status and execution order (G0–G9) in
  `docs/dev/v1-gap-analysis.md` — consult when planning, and keep both updated.
- **Attribution**: when drawing on external tools/UIs for inspiration or code, record it in
  `docs/references.md`; never vendor incompatibly-licensed code (e.g. GPL) into this MIT project.

Detailed local guidance lives in `frontend/CLAUDE.md` and `src/draftpilot/{worker,core}/CLAUDE.md`.
`AGENTS.md` mirrors this file for Codex compatibility.
