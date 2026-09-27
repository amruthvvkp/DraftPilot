---
name: web-frontend
description: Work on the DraftPilot React/Vite studio (frontend/) — pages, components, API client, styles, and how FastAPI serves the build. Use when changing UI behavior or structure.
---

# Web frontend (DraftPilot)

The studio is a React 19 + Vite + TypeScript SPA in `frontend/`. The FastAPI web process
(`src/draftpilot/api/app.py:create_app()`) serves the built bundle and exposes every HTTP route
under `/api/v1`. The browser never touches Postgres/Redis directly — it only calls the API.

## Layout

- `frontend/src/main.tsx` — entry; mounts `<App />` inside `AuthGate` (`SignIn.tsx`) and imports `styles.css`.
- `frontend/src/App.tsx` — path-regex routing on `window.location.pathname`
  (`/projects`, `/projects/:id`, `/projects/:id/studio`, `/projects/:id/context`, `/settings`).
- `frontend/src/api.ts` — typed API client: shared `request<T>()` helper (JSON, same-origin
  credentials, `ApiError`, dispatches `AUTH_REQUIRED_EVENT` on 401) plus one exported function per call.
- `frontend/src/*.tsx` — pages/panels (`Workspace.tsx`, `ArtifactStudio.tsx`, `ProviderSettings.tsx`, ...).
- `frontend/src/*.css` — `styles.css` (global) plus feature sheets (`timeline.css`, `backup.css`,
  `provider-settings.css`).
- `frontend/public/` — favicons, logo, `site.webmanifest` (copied verbatim into the build).
- `frontend/vite.config.ts` — outputs `dist/`; dev server on :5173 proxies `/api` to `:8000`.

## Serving

`npm --prefix frontend run build` writes `frontend/dist`. `create_app()` mounts `dist/assets` at
`/assets` and returns `index.html` for any other non-API path (SPA fallback). The path comes from
`WEB__FRONTEND_DIST` (`WebSettings.frontend_dist`); if the build is missing the app logs a warning.

## Add a page

1. Create `frontend/src/MyPage.tsx` exporting a default component with typed props.
2. Add a route match in `App.tsx` (e.g. `path.match(/^\/projects\/(\d+)\/my-page$/)`).
3. Link to it with a plain `<a href>` (full-page navigation; no client router).

## Add an API call

1. Backend: add the endpoint in a module under `src/draftpilot/api/` and include its router on the
   `protected` router in `src/draftpilot/api/__init__.py` (gated by `require_api_auth`; optional `API__TOKEN`).
2. Frontend: add a type and a function in `api.ts` that calls `request<T>('/api/v1/...')`. Never
   call `fetch` ad hoc from components.

## Run

```bash
uv run python -m draftpilot.api       # API + built SPA on :8000
npm --prefix frontend run dev          # Vite HMR on :5173 (proxies /api to :8000)
npm --prefix frontend run build        # tsc --noEmit + vite build -> frontend/dist
```

In Docker, the `ui` service serves the build on :9000; `compose.dev.yml` mounts `./frontend/dist`,
so rebuild locally and reload the page.

## Verify

- `npm --prefix frontend run build` — typecheck and build must pass.
- `uv run pytest tests/e2e` — Python Playwright journeys against :9000
  (first run `uv run playwright install chromium`), or `docker compose --profile test run --rm e2e`.
- Backend changes: `uv run pytest`, `uv run mypy src`, `uv run ruff check`, `uv run interrogate src migrations`.

## Conventions

- Use accessible roles and labels (`<button>`, `<label>`, `aria-label`, headings) — the e2e tests
  select by `get_by_role` / `get_by_label` / `get_by_text`, so renaming visible text breaks them.
- No secrets in the browser: provider keys and tokens stay server-side; the UI only holds the session.
- E2E tests mock the API with `page.route("**/api/v1/...", handler)` and never depend on live DB state.
- Keep styles in the CSS files (class names, CSS variables), not inline color literals.
