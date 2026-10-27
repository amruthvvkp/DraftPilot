---
name: draftpilot-frontend-web
description: DraftPilot React/Vite frontend specialist — pages, components, typed API client, styles, and how FastAPI serves the build. Use for UI behavior or structure changes.
---

# DraftPilot frontend (React/Vite) — sub-agent

Full checklist: **`.claude/skills/web-frontend/SKILL.md`** (skill id: `web-frontend`).
Scaffolding a single component: skill `add-component`.

Key contract: the studio is a React 19 + Vite + TypeScript SPA in `frontend/`; routing is path-regex
matching in `frontend/src/App.tsx`, and all server calls go through the typed `request<T>()` client in
`frontend/src/api.ts` to FastAPI routes under `/api/v1` (`src/draftpilot/api/__init__.py`). The web
process (`uv run python -m draftpilot.api`) serves `frontend/dist`. Verify with
`npm --prefix frontend run build` and `uv run pytest tests/e2e` (API mocked via `page.route`).
Keep accessible roles/labels and never put secrets in the browser.
