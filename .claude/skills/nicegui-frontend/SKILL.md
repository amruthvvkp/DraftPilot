---
name: nicegui-frontend
description: Work on the DraftPilot NiceGUI frontend — pages, layout, theme, reusable components, async/blocking mechanics, per-client state. Use when changing UI behavior or structure (for scaffolding a single component or page, see add-component / add-model).
---

# NiceGUI frontend (DraftPilot)

DraftPilot is **single-process**: `from nicegui import app` IS the FastAPI app. There
is no separate backend service and no HTTP `APIClient` — pages talk to Postgres/Redis
directly through `draftpilot.core` and `draftpilot.crud`, and enqueue background work
onto the ARQ pool. Read `src/draftpilot/ui/CLAUDE.md` first.

## Structure

- `ui/theme/design.py` — design tokens; `quasar_colors()` brands Quasar.
- `ui/theme/layout.py` — `register_assets()` (startup) + `with_layout` (per-page chrome:
  logo header, sidebar, 3-state theme toggle, favicon). Nav lives in `NAV_ITEMS`.
- `ui/components/` — reusable library (`from draftpilot.ui import components as c`);
  showcase every component in `components/design_system.py`.
- `ui/pages/` — one `content()` builder per route (sync or async).
- `ui/main.py` — routes (`ui.page(path)(with_layout(...))`) + `app.on_startup/shutdown`.

## Mechanics that matter

- **Routes**: register in `main.py`; wrap with `with_layout` (it supports async builders
  and forwards path params, e.g. `/screenplay/{screenplay_id}`).
- **DB access**: `async with session_scope() as session:` + the `crud` helpers. Never
  block the event loop.
- **Blocking / CPU work**: `await run.io_bound(fn, ...)` or `await run.cpu_bound(fn, ...)`
  (`from nicegui import run`) — never call blocking code directly in a handler.
- **Background work that updates UI**: prefer `background_tasks.create(coro)` over bare
  `asyncio.create_task`; for long jobs, enqueue ARQ via `await (await get_arq_pool()).enqueue_job(...)`
  and read results back from Redis cache.
- **Dynamic regions**: rebuild with `container.clear()` inside the container context, or use
  `@ui.refreshable` + `.refresh()`.
- **Value elements**: pass `on_change=` in the constructor; after construction use
  `.on_value_change(...)`.
- **Per-client state**: `app.storage.client` (per tab) / `app.storage.user` (per browser,
  needs `storage_secret`). The theme toggle persists in `app.storage.user["theme"]`.
- **Styling**: use `dp-*` classes and the CSS variables in `static/styles.css`; brand colors
  come from `design.py`. Don't hard-code colors inline.

## Code style

Every module, class, function, and nested function needs a one-line Sphinx docstring, and every
signature needs full type hints (`-> None` when nothing is returned). Interrogate enforces 100%
and mypy must stay clean.

## Verify

`uv run python -m draftpilot.ui.main` then open `http://localhost:8000` (or `:9000` via
Docker). Check `/design-system` renders. Imports: `uv run python -c "import draftpilot.ui.theme, draftpilot.ui.components"`.
