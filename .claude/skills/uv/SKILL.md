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
uv sync --group ui        # NiceGUI app: nicegui, pydantic-ai, sqlmodel, asyncpg, redis, arq, alembic, otel
uv sync --group worker    # ARQ worker (includes the ui group)
uv sync --group mcp       # FastMCP server
uv sync --group dev       # lint + test + docs tooling
```

- `debugpy` — added to images only when `INSTALL_DEBUGPY=true` (see `compose.dev.yml`).
- `otel` — Logfire instrumentation extras; pulled in via the `ui` group.

Add a dependency to a specific group: `uv add --group ui <pkg>`.

## Key commands

```bash
uv add <pkg>                 # add a dependency (never pip install)
uv add --group ui <pkg>      # add to a specific group
uv remove <pkg>              # remove a dependency
uv lock                      # refresh the lockfile
uv sync --group ui           # install from the lockfile
uv run <command>             # run inside the project environment
uv run python -c "..."       # run Python in the environment (never bare python)
uvx <tool>@<version> <args>  # run a CLI tool without installing it
```

## Common patterns

```bash
# Bad → Good
pip install requests   → uv add requests
python script.py       → uv run script.py
python -m draftpilot.ui.main  → uv run python -m draftpilot.ui.main
```

After changing dependencies, the Docker build uses `uv sync --frozen`, so always
`uv lock` and commit `uv.lock`.

## Documentation

- https://docs.astral.sh/uv/llms.txt
