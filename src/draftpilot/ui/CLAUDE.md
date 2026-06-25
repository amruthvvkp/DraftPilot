# UI — NiceGUI frontend

`from nicegui import app` returns the underlying FastAPI app. Lifecycle resources (DB tables, Redis,
ARQ pool) are wired in `main.py` via `app.on_startup` / `app.on_shutdown`. There is no separate API
service.

## Structure

- `theme/design.py` — design tokens (colors, fonts, spacing, radii). `quasar_colors()` brands Quasar.
- `theme/layout.py` — `register_assets()` (startup: static mount + shared fonts/CSS) and `with_layout`
  (per-page: `ui.colors`, header, sidebar, 3-state theme toggle persisted in `app.storage.user`).
- `static/styles.css` — CSS custom properties mirroring the tokens; light on `:root`, dark on
  `.body--dark`. Component classes are prefixed `dp-`.
- `components/` — reusable library; import via `from draftpilot.ui import components as c`.
- `components/design_system.py` — living style guide. Add a component → showcase it here.
- `pages/` — one `content()` builder per route (sync or async). Routes registered in `main.py`.

## Adding a page

1. Write `pages/<name>.py` with `def content():` or `async def content():`.
2. Register in `main.py`: `ui.page("/path")(with_layout(<name>.content))`.
3. Add a sidebar entry to `NAV_ITEMS` in `theme/layout.py` if it should be navigable.

## Adding a component

Add a helper to the relevant `components/*.py`, export it from `components/__init__.py`, and render it
in `design_system.py`. Style with `dp-*` classes / token CSS variables, not inline colors.

## DB access in pages

Use `async with session_scope() as session:` (from `draftpilot.core.db`) and the `crud` helpers.
Enqueue background work with `await (await get_arq_pool()).enqueue_job("<task>", ...)`.
