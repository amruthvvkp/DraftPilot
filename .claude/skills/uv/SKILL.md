---
name: uv
description: Guide for using uv, the Python package and project manager. Use this when working with Python projects, scripts, packages, or tools in DraftPilot.
---

# uv

uv is an extremely fast Python package and project manager. It replaces pip,
pip-tools, pipx, pyenv, virtualenv, poetry, etc. **DraftPilot is a uv project**
(`uv.lock` at the root, Python pinned to 3.13).

## When to use uv

**Always use uv for Python work** here. Never call `pip` or bare `python`.

## DraftPilot dependency groups

Dependencies are organized into groups in `pyproject.toml`. Install what you need:

```bash
uv sync --all-groups      # everything (app + worker + mcp + rag + dev tooling)
uv sync --group web       # web app: fastapi, uvicorn, pydantic-ai, sqlmodel, asyncpg, redis, arq, alembic, otel
uv sync --group worker    # ARQ worker (includes the web group)
uv sync --group mcp       # FastMCP 4 server (includes web + otel)
uv sync --group rag       # standalone RAG service
uv sync --group dev       # lint + test + e2e (Playwright) + docs tooling
```

- `debugpy` — added to images only when `INSTALL_DEBUGPY=true` (see `compose.dev.yml`).
- `otel` — Logfire instrumentation extras; pulled in via the `web` group.

Add a dependency to a specific group: `uv add --group web <pkg>`. Frontend (npm) dependencies live
in `frontend/package.json`, not in uv.

## Key commands

```bash
uv add <pkg>                 # add a dependency (never pip install)
uv add --group web <pkg>     # add to a specific group
uv remove <pkg>              # remove a dependency
uv lock                      # refresh the lockfile
uv sync --all-groups         # install from the lockfile
uv run <command>             # run inside the project environment
uv run python -c "..."       # run Python in the environment (never bare python)
uvx <tool>@<version> <args>  # run a CLI tool without installing it
```

## Common patterns

```bash
# Bad → Good
pip install requests   → uv add requests
python script.py       → uv run script.py
python -m draftpilot.api  → uv run python -m draftpilot.api
pytest -m lmstudio       → uv run pytest -m lmstudio
```

After changing dependencies, the Docker build uses `uv sync --frozen`, so always
`uv lock` and commit `uv.lock`.

## Documentation

- https://docs.astral.sh/uv/llms.txt
