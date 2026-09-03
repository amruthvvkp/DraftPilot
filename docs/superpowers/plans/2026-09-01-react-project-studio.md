# React Project Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the NiceGUI project-vault surface with a modern React/Vite SPA served by the existing FastAPI process, preserving the current project and screenplay workflows.

**Architecture:** Vite builds a static React application into `frontend/dist`. FastAPI remains the single web process and serves `/assets/*`, `/api/*`, and the SPA fallback; the existing SQLModel/CRUD layer remains the source of truth. The first slice ports project browsing and creation through a small JSON API, while the existing NiceGUI editor remains available until later slices migrate it.

**Tech Stack:** React 19, TypeScript, Vite, Vitest, FastAPI/Starlette, SQLModel, NiceGUI during transition.

**Spec:** `docs/roadmap.md` and the approved DraftPilot modernization plan.

## Global Constraints

- Keep the application local-first and single-user.
- Keep FastAPI, Postgres, Redis, ARQ, MCP, and the existing SQLModel domain models.
- Serve the SPA from the same origin as `/api`, with API routes taking precedence over the fallback.
- Keep credentials out of the frontend and preserve prefixed environment configuration.
- Preserve unrelated worktree changes and use `uv` for Python commands.
- Maintain Ruff, mypy, interrogate, and test gates.

### Task 1: Add the frontend package and tested API client boundary

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/api.test.ts`

**Interfaces:**
- Produces `Project`, `ProjectCreatePayload`, `listProjects()`, and `createProject()` for the UI.

- [ ] **Step 1: Write failing API-client tests** for GET and POST request shapes using Vitest's fetch stub.
- [ ] **Step 2: Run `npm test -- --run src/api.test.ts` and verify failure because the package is not implemented.**
- [ ] **Step 3: Implement the Vite package and typed API client with explicit error handling for non-2xx responses.**
- [ ] **Step 4: Run the focused Vitest test and confirm it passes.**

### Task 2: Add versioned project REST endpoints

**Files:**
- Create: `src/draftpilot/api/__init__.py`
- Create: `src/draftpilot/api/projects.py`
- Modify: `src/draftpilot/ui/main.py`
- Create: `tests/test_projects_api.py`

**Interfaces:**
- Produces `GET /api/v1/projects` returning `list[ProjectRead]`.
- Produces `POST /api/v1/projects` accepting `ProjectCreate` and returning `ProjectRead`.

- [ ] **Step 1: Write failing endpoint tests for empty listing, valid creation, and missing title rejection.**
- [ ] **Step 2: Run `UV_CACHE_DIR=/private/tmp/draftpilot-uv-cache uv run --group ui pytest tests/test_projects_api.py -q` and verify failure because routes are absent.**
- [ ] **Step 3: Implement an APIRouter using `async_get_db`, the existing CRUD functions, and Pydantic response models; register it before UI routes.**
- [ ] **Step 4: Run the focused endpoint tests and confirm they pass.**

### Task 3: Serve and build the React shell

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles.css`
- Modify: `src/draftpilot/ui/main.py`
- Modify: `Dockerfile.ui`
- Modify: `compose.yml`

**Interfaces:**
- Produces a same-origin SPA at `/projects` with a fallback for client-side routes.
- Keeps `/screenplay/{screenplay_id}` available during migration.

- [ ] **Step 1: Add a shell render test covering the project route and creation entry point.**
- [ ] **Step 2: Run the frontend test and verify it fails because the React shell is absent.**
- [ ] **Step 3: Implement the shell, project vault, empty state, responsive navigation, and API-backed create flow.**
- [ ] **Step 4: Configure FastAPI static serving and SPA fallback, then update the container to build frontend assets.**
- [ ] **Step 5: Run Vitest, TypeScript, the Python gates, and `docker compose build ui`.**

### Task 4: Port the project wizard and validate the running stack

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/projectWizard.test.tsx`
- Modify: `docs/roadmap.md`
- Modify: `README.md`

**Interfaces:**
- Produces a React wizard collecting title, story metadata, all supported genres, a primary
  screenplay language, multiple dialogue-translation languages (including Indian languages),
  typed references, artwork URL, and upload metadata.

- [ ] **Step 1: Write failing component tests for required title validation, step navigation, and submitted payload.**
- [ ] **Step 2: Run the focused component tests and verify failure.**
- [ ] **Step 3: Implement the sleek wizard and project cards against the typed API client.**
- [ ] **Step 4: Rebuild and start Compose, then smoke-test `/projects` and project creation in the browser/API.**
- [ ] **Step 5: Update documentation and mark only this first frontend slice complete.**

## Self-review

- This plan deliberately covers the first React vertical slice only; screenplay editor, providers, agent teams, backups, and observability remain separate follow-up plans.
- All named files and interfaces are concrete.
- API and frontend tests precede their implementations.
