# v1 gap analysis

!!! info "Baseline"
    Branch `amruthvvkp/issue15` at `ab451ff` (2026-09-27). Every status here was checked against the
    code and by running the suites, not against docs or commit messages. This analysis replaces the
    greenfield milestone list in the v1 plan: work builds on what exists and does not rewrite it.

The v1 goal is a complete, agent-first screenwriting studio. A single writer works with a
**digital writers' room**: a coordinated team of agents that covers story bouncing, ideation, scene
writing, outline improvement, rewrites and audience evaluation. The room is grounded in a **Story twin**
and a **Writer twin**. Full manual editing must keep working. The MCP server is the one tool surface
shared by in-app and external agents (Claude Code, Codex). All LLM-backed tests and evals run against a
local LM Studio.

Legend: ✅ done · 🟡 partial · ❌ missing · 🔴 broken.

## Progress

| Step | Status | Commit | Notes |
|---|---|---|---|
| G0 · Restore green | ✅ done | `8b27c0c` | 148 unit, 15 e2e, 1 LM Studio (Tier 1) test passing; ruff, mypy and interrogate clean |
| G1 · Security | ✅ done | `f585ea5` | REST token auth and browser session; MCP writes need a writer-decided, argument-bound, single-use approval (verified live); proposal reject; fixed the unreachable `translation.propose` |
| G2 · Remove NiceGUI | ✅ done | `be5380e` | FastAPI `create_app()` + uvicorn (`python -m draftpilot.api`); `WEB__` settings; `web` group; SPA fallback confined to `dist`; removed startup `create_db_and_tables()`; docs, skills and agents updated |
| G3 · Data backbone | ✅ done | `60269c9` | Id-stable revision restore (translations no longer lost); block `origin` (human/import/proposal); persisted title page; 3-query document load; whole-scene RAG text (was: last-edited block only); block delete and reorder; draft switcher (imported drafts were unreachable); SSE live sync over Redis pub/sub (verified live on Big Fish) |
| G4 · Agent platform | ✅ done | `e2a7f42` | Room runtime: YAML role specs, typed deps, in-app agents use DraftPilot's own MCP server as an internal client scoped to one project (approval-required writes still go to the writer); `read_project_overview` + paged scene reads (Big Fish previously exceeded the output limit); LM Studio default with `auto` model and trusted `host.docker.internal` (containers previously couldn't reach it); Anthropic and Google providers; model discovery; streamed Vercel v6 room chat; `AgentRun` metrics with trace ids. Verified live and in Tier 1 on qwen3.8-27b |
| G5 · RAG | ✅ done | `3decb98` | Hybrid retrieval: paragraph-aware chunks with offsets; LM Studio embeddings (nomic-embed-text-v1.5, 768-d) through PydanticAI `Embedder`; pgvector HNSW + tsvector GIN fused with RRF (Postgres image = postgres:16-alpine + pgvector, so existing data and collations are preserved); SQLite FTS5 backend for tests and offline use; degrades to full-text when embeddings are down; project reindex job and endpoint; imports are now indexed (previously never). Big Fish: 192 docs, 250 chunks, 4.8 s |
| G6a · Twins | ✅ done | `c6014be` | Story twin derived from the working draft into the knowledge graph (idempotent; never overwrites writer-edited nodes; debounced refresh on scene changes); server-side Writer twin (profile, memories, learned approve/reject decisions); both briefs in every room agent's instructions; `read_story_twin` MCP tool. Big Fish: 48 characters, 148 locations |
| G6b/c · Room team and workflows | ✅ done | `879de52` | 13 role specs (showrunner + 12 specialists; the showrunner delegates with a `consult` tool). Eight `pydantic_graph` workflows: notes→outline and scene rewrite (evaluator-optimizer loops), outline→scenes, character arcs, brainstorm and audience panel (parallel fan-out with joins), coverage and continuity. Durable worker runs with a live trail and cancellation; they end in proposals or a report. New reversible proposal kinds: whole-scene rewrite (id-stable) and appended scenes. MCP `list_room_workflows`/`start_room_workflow`; Writers' room page. Scene reads now default to compact Fountain (about 5× smaller). Self-contained loop steps run without tools, and graders run without reasoning (`LLM__THINKING` overrides this). Live on qwen3.8-27b: showrunner 18 min → 6 min; Big Fish rewrite passes, with the script doctor scoring it 8/10 (draft 13 min with reasoning, critiques under 1 min each) |
| G7 · Evals and usefulness | ✅ done | `879de52` | `python -m draftpilot.evals`: four `pydantic_evals` suites (room Q&A, rewrite, notes→outline, planted continuity error) on an isolated Big Fish project with a local index, using deterministic evaluators plus an LM Studio `LLMJudge`, and baselines in `evals/baselines/`. Online checks on every workflow result. Usefulness: acceptance, retention (via block authorship), thumbs, cost and reliability per workflow and role (`/insights`, Writers' room table). Langfuse scores for feedback, decisions and checks |
| G8 · Frontend | 🟡 mostly done | `15c73e6`, `ea85935` | Every colour is a theme token (Paper, Slate, Night, System, custom accent; saved to the Writer twin). Vault delete (backup first, metadata-driven purge), duplicate and restore. Streaming room chat (AI SDK v6 `useChat`, live tool chips). Story twin page. Editor layout fixed (full-width text, hover tools, page-break dividers, auto-height, docked snapshots, header nav). Pinned deps; Vitest in CI. Beat board over the Outline's beats. Smart typing in the block editor (unit-tested, verified on the real stack). **Open:** rich-text editing (inline bold and italics, via TipTap), client router and data layer |
| G9 · Docs and verification | ✅ done | this commit | Zensical user guide (start, editor, story tools, room, settings, checklist), advanced guides, developer guide (architecture, standards, extending the room), a generated HTTP API reference (checked by a test), a mkdocstrings Python reference, and a strict docs build in CI. A real-stack browser smoke test on Big Fish (`-m stack`, no mocks) passes; it found and fixed a PDF export crash on apostrophes. Eval baselines on qwen3.8-27b: room Q&A 100%, continuity 100%, outline 100%, rewrite 83% (the evals found and drove fixes for a lenient judge, rewrites ignoring length or adding speakers, and runaway reasoning) |

Found along the way (now fixed in G8): no project delete or duplicate endpoint; the "Review format" buttons squeezed the text column; the floating Snapshots panel and launch buttons overlapped the context rail; page breaks rendered as empty text boxes. Raw `**bold**` Fountain markup remains visible until the rich-text editor lands.

## Suite baseline

| Check | Result |
|---|---|
| `pytest tests --ignore=tests/e2e` | 🔴 130 passed, **2 failed** (`test_monty*`), **1 collection error** (`test_mcp_client.py`) |
| `pytest tests/e2e` (Playwright) | ✅ 15 passed, but every API call is mocked (`page.route` → `fulfill`), so no test drives the real backend |
| `ruff check src migrations` | ❌ 146 errors (59 auto-fixable; mostly B008, I001, UP043, UP017) |
| `mypy src` | ❌ 6 errors in 4 files |
| `interrogate src migrations` | ✅ 100% |
| Frontend unit tests | ❌ none (`npm test` only echoes a message) |
| LLM evals | ❌ none |

## Regressions from the dependency bump (`ab451ff`)

These are blockers and get fixed first.

1. 🔴 **MCP client import fails.** `core/mcp_client.py:12` imports `streamablehttp_client`, which
   MCP SDK 2 removed (it is now `streamable_http_client`). `read_resource` also now takes `str`, not
   `AnyUrl` (`:161`).
2. 🔴 **Monty sandbox fails.** `core/monty.py:105` passes a `dict` where the new API expects a
   `ResourceLimits` object. Both `test_monty*` failures trace to this.
3. 🟡 **Type errors in copilot and worker.** mypy flags `api/copilot.py:142` and
   `worker/functions.py:355`, where the `CopilotMessageCreate` field types (`citations`,
   `instruction_layers`) no longer line up.

## Correctness and security defects found by the audit

- 🔴 **Real PDF imports fail over HTTP.** `api/exports.py:116` decodes the body as UTF-8 before it
  checks the format, so a binary PDF raises `UnicodeDecodeError` and the endpoint returns 422. The only
  API test sends malformed bytes, so it never catches this.
- 🔴 **Writer approval can be bypassed over MCP.** `core/authorization.py:49` enforces
  `approval_required` capabilities by checking `request.approved`, but MCP tools take that value from
  the calling client (`approved: bool = False` in `mcp/server.py:283,373,678`). An external agent can
  approve its own writes.
- 🔴 **The REST API has no authentication.** Only the `/api/v1/mcp` admin routes check a bearer token.
  Provider settings, backup and restore, and all project routes are open.
- 🟡 **Block ids change on restore and import.** Revision restore and screenplay import/backup restore
  delete every block and insert new ones (`core/screenplay/hydrate.py:60`, `:90`). That breaks
  references to those blocks, including proposals and citations.
- 🟡 **Artwork mount depends on the frontend build.** `/artwork` is only mounted when `frontend/dist`
  exists (`ui/main.py`).

## Status by area

### Platform and hosting

| Item | Status | Evidence / remaining work |
|---|---|---|
| NiceGUI removed | ❌ | NiceGUI's `app` is still the FastAPI host (`ui/main.py`, `ui.run()`). Telemetry instruments it (`core/telemetry.py:52`); compose and Dockerfiles start `draftpilot.ui.main`. Needed: an `api/app.py` `create_app()` with a lifespan (redis, arq, db) replacing `ui/main.py` (routers, `/health`, `/assets`, `/artwork`, SPA fallback registered last, favicon moved into `frontend/public`); move `ui/project_wizard.py`; delete `ui/`; remove nicegui from pyproject and rename the `ui` group; update compose, the Dockerfiles, CLAUDE.md, AGENTS.md, README and the `.claude` skills and agents |
| FastMCP 4 / MCP SDK 2 | 🟡 | Upgraded, but the client is broken (see regressions) |
| Logfire MCP instrumentation | ❌ | `core/telemetry.py:58` is a `pass`. Needed: a guarded `instrument_mcp()` helper, relying on native MCP OTel spans until then |
| Langfuse | 🟡 | OTLP export to the bundled Langfuse only. No scores, and no run or proposal ids on spans |
| Live sync (SSE, Redis pub/sub) | ❌ | Edits made by agents or MCP only appear after a refetch. A stale editor gets a 409 on its next save |
| REST auth | ❌ | See defects |

### Data model

| Item | Status | Evidence / remaining work |
|---|---|---|
| Project → Screenplay → Act → Scene → Block | ✅ | Plus DialogueTranslation, SceneRevision |
| Optimistic concurrency | ✅ | `Scene.version` with If-Match (428/409); Project, Reference, Artifact and KnowledgeNode are versioned too |
| Stable block ids | 🟡 | Per-block PATCH keeps ids stable; restore and import don't (see defects). There's no block delete or reorder route |
| Block origin / authorship | ❌ | Needed to measure retained agent text |
| Title page persisted | ❌ | Parsed from Fountain, then dropped on save |
| Story entities | 🟡 | Stored as generic `StoryArtifact` kinds plus `KnowledgeNode/Edge`. There are no first-class Character, Location, Outline/Beat, Note or Bible records. **Decision:** keep the knowledge graph as the Story twin store and add typed node schemas, rather than creating parallel tables |
| Writer twin | ❌ | The "writer profile" lives only in browser localStorage (`frontend/src/ProviderSettings.tsx`) |
| Usefulness data | ❌ | Missing: feedback on messages and proposals, run usage, model, cost and latency on `WorkflowRun` |

### Import and export

| Item | Status | Evidence / remaining work |
|---|---|---|
| Fountain import/export | ✅ | Big Fish: 191 scenes, 2242 blocks, title page parsed |
| FDX import/export | ✅ | Big Fish `.xml`: 203 scenes, 2568 blocks. The scene count differs from Fountain and needs investigating |
| PDF import | 🔴 | Fails over HTTP (see defects). The pypdf heuristic parser only produces action, character and dialogue blocks: Big Fish gives 193 scenes, and 2943 of its 4476 blocks come out as "dialogue". Needs pdfplumber x-position classification |
| PDF / HTML export | ✅ | ReportLab / safe HTML |
| Notes import (.txt/.md/.docx) | ❌ | Needed for "start from notes" |
| Multi-act import | ❌ | Imports always produce a single act |

### MCP server

| Item | Status | Evidence / remaining work |
|---|---|---|
| Tool surface | ✅ | 23 tools, 6 resources, 1 prompt, typed through the capability service. Remove the leftover `greet` placeholder |
| Transports | ✅ | stdio plus separate HTTP (compose :9001). Not mounted in the web app, which is optional |
| Auth, grants, audit | ✅ | Static and per-client bearer tokens, per-project grants, redacted audit log |
| Human approval | 🔴 | Client-supplied `approved` flag (see defects). Writes must become proposals that the writer approves in the UI |
| In-app agents use MCP | ❌ | `core/copilot.py` creates a tool-less `Agent`; `core/mcp_client.py` is only used by tests |

### Agents: the writers' room

| Item | Status | Evidence / remaining work |
|---|---|---|
| Roles | 🟡 | 7 roles (`core/agent_roles.py`), but they're only a label and one sentence each. There are just 3 `Agent(...)` call sites in the codebase, and the role is injected as "You are the {role}" |
| Orchestrator / Showrunner | ❌ | No delegation, `pydantic_graph` or sub-agents |
| PydanticAI features | ❌ | Only `OpenAIChatModel` and `instrument_pydantic_ai` are used. No deps/RunContext, tools, toolsets/MCPToolset, output validators or ModelRetry, capabilities, deferred approvals, UsageLimits, FallbackModel, streaming, `Agent.from_file` specs or Embedder |
| Workflows | 🟡 | Wizard assist, single-shot context workflows, copilot chat. Runs are durable (retry, resume, cancel). Missing: notes→script, brainstorm, character arcs, outline improvement, the rewrite loop (evaluator-optimizer), audience persona panel, coverage, LLM continuity. Evaluator names in workflow specs are never invoked |
| Proposal review | 🟡 | Approve and rollback with version checks. **No reject endpoint.** Proposals render as raw JSON |
| Providers | 🟡 | openai, openrouter, gateway, ollama and lm_studio, all through `OpenAIChatModel` with no LM Studio profile (strict tools stay on). Missing: model listing, native Anthropic/Google. The SSRF guard blocks LM Studio on a LAN host. Keys are encrypted |

### RAG

| Item | Status | Evidence / remaining work |
|---|---|---|
| Service | 🟡 | A separate FastAPI service with bearer auth and versioned citations; approved changes re-index incrementally |
| Embeddings | ❌ | A 128-dimension hashed bag-of-words, which isn't semantic. Needed: PydanticAI `Embedder` on LM Studio `/v1/embeddings` |
| Storage / search | ❌ | SQLite with a full scan per project; cosine *or* lexical search, no chunking. Needed: pgvector HNSW plus Postgres full-text search, fused with reciprocal-rank fusion, and chunking with offsets |

### Evals and usefulness measurement

| Item | Status | Evidence / remaining work |
|---|---|---|
| `pydantic_evals` suites | ❌ | Needed: an `evals/` dataset per role and workflow, an LM Studio judge, baselines and thresholds, a `draftpilot-evals` runner |
| LM Studio test tier | ❌ | Needed: a `pytest -m lmstudio` marker that auto-discovers models; no pytest markers exist today |
| Online evals | ❌ | Needed: the `OnlineEvaluation` capability on sampled runs |
| Benchmark | 🟡 | Structural manifest comparison (`core/benchmark.py`), without thresholds |
| Usefulness metrics | ❌ | No accept or reject rates, ratings, retained-text ratio, Langfuse scores or insights view |

### Frontend and UX

| Item | Status | Evidence / remaining work |
|---|---|---|
| Stack hygiene | ❌ | Every dependency is pinned to `"latest"` and build tools sit in `dependencies`. No router (regex on the pathname, full-page reloads), no data layer, no component library. Some JSX lines are thousands of characters long |
| Editor | 🟡 | A `<textarea>` plus a `<select>` per block. Missing: element-flow smart typing, shortcuts, find/replace, command palette, real pagination and page count, focus/typewriter modes. Dual dialogue is highlighted, not laid out side by side |
| Navigator / reorder | ✅ / 🟡 | The scene navigator is done. Reorder only works on the timeline board, and it goes through a proposal |
| Copilot UX | 🟡 | Role, permission and model pickers exist. The Copilot polls instead of streaming. Missing: a diff view, reject, feedback, a room activity view |
| Story development UI | 🟡 | Artifact studio and a knowledge-graph card grid. No character, location, notes-board, bible or beat-board views |
| Theming | ❌ | Hard-coded hex colours; no tokens, modes, palettes or settings |
| Start options | 🟡 | Blank and wizard are done. Import is only reachable from inside a workspace; "from notes" is missing |

### Docs and tooling

| Item | Status | Evidence / remaining work |
|---|---|---|
| User guide | ❌ | `docs/index.md` is Zensical boilerplate; nothing covers the editor, the room or the wizard |
| Developer guide | 🟡 | Topic pages exist (mcp, testing, context-workflows, deployment, providers, monty, backups), but several aren't in the nav. No architecture, standards, API or MCP reference, agents or evals pages. mkdocstrings isn't configured and the docs CI is disabled |
| `zensical.toml` | 🟡 | Still the template, with a stray `link =` at line 308 |
| `.claude` skills and agents | ❌ | `nicegui-frontend`, `add-component`, `run-stack`, `uv` and the `draftpilot-frontend-nicegui` agent still describe NiceGUI |

## Execution order

Each step ends with the suite green, is committed referencing #15, and is pushed.

1. **G0 · Restore green:** MCP SDK 2 client fix, Monty `ResourceLimits`, mypy clean, ruff clean (auto-fix plus the reviewed B008 FastAPI `Depends` pattern), PDF decode fix with a real Big Fish PDF API test, pytest markers (`unit`, `e2e`, `lmstudio`).
2. **G1 · Security:** REST bearer auth; MCP writes become proposals that need approval in the UI (drop the client-supplied `approved`); proposal reject endpoint.
3. **G2 · Remove NiceGUI:** `create_app()` factory, lifespan, telemetry, compose and Docker, docs and tooling.
4. **G3 · Data backbone:** block `origin`, title page, id-preserving restore and import, block delete and reorder, SSE live sync over Redis pub/sub.
5. **G4 · Agent platform:** LM Studio provider profile and model listing, per-role YAML specs, typed deps, in-app agents on `MCPToolset`, streaming chat (Vercel adapter), usage and model recorded on runs.
6. **G5 · RAG:** Embedder on LM Studio, pgvector plus full-text hybrid search, chunking.
7. **G6 · Writers' room:** Showrunner delegation, Story twin typed nodes and Twin Keeper extraction, server-side Writer twin, graph workflows (notes→script, brainstorm, arcs, outline, rewrite loop, audience panel, coverage, continuity).
8. **G7 · Evals and measurement:** `pydantic_evals` suites and baselines on LM Studio, online evals, feedback, usefulness metrics, Langfuse scores, insights UI.
9. **G8 · Frontend modernisation:** pinned deps, router plus data layer, component library and design tokens, theming, ProseMirror/TipTap editor with smart typing, beat board, story twin views, diff review, room activity, Vitest, e2e against the real backend.
10. **G9 · Docs and verification:** Zensical user guide (basic and advanced) and developer guide (architecture, standards, API and MCP reference, agents, evals), docs CI, browser smoke test on Big Fish, manual test checklist.

## Plan changes (2026-09-27)

Four changes arrived after G0–G9 had shipped. They were written against the superseded milestone list
(M0–M11), so each is re-targeted below as a follow-up step on the code that exists. The milestones
map to steps as follows: M0→G0, M1→G2/G8, M2→G3, M3–M4→G8, M5→G6a, M6→G1/G4, M7→G4/G5,
M8→G6b, M9→G6c, M10→G7, M11→G9. Every step keeps the suite green, references #15 and is pushed with
`gh`. After each push, `gh run watch` checks the run (CI exists: `ci.yml`, `docs.yml`).

| Step | Status | From | Scope |
|---|---|---|---|
| G10 · SPA hosting | ⏳ planned | change 4 | `app.frontend()`, cache headers, auth scoped to `/api` |
| G11 · Temporal, Langfuse out | ⏳ planned | change 1 | Durable execution on Temporal; ARQ, `pydantic_graph` workflows and Langfuse removed |
| G12 · Frontend telemetry | ⏳ planned | change 3 | `@pydantic/logfire-browser` plus a same-origin OTLP proxy |
| G13 · Monty code mode | ⏳ planned | change 2 (M8b) | CodeMode roles, `analyze_script`, continuity rules as code, DynamicWorkflow |

Order: G10 (small and independent), then G11 (the largest; G12's workflow spans and G13's durable
execution depend on it), then G12 and G13.

### G10 · SPA hosting (change 4)

- FastAPI is already pinned `>=0.141.1`, and `FastAPI.frontend()` is available. In `api/app.py`,
  replace `_spa_file` and the catch-all route with
  `app.frontend("/", directory=settings.web.frontend_dist, fallback="index.html", check_dir=settings.web.require_frontend)`,
  registered after the routers. Keep the existing `WEB__FRONTEND_DIST` name (the plan's `static_dir`)
  rather than renaming it. Add `WEB__REQUIRE_FRONTEND` (default `false`; `true` in `Dockerfile.ui`).
- Auth goes on the `/api` router only, never on the app, so the SPA shell and token prompt still load.
  MCP runs as its own service (:9001) with its own bearer auth. If it is ever mounted at `/mcp`, the
  auth dependency goes on that mount.
- Middleware: `Cache-Control: public, max-age=31536000, immutable` for `/assets/*`, and `no-cache`
  for `index.html`.
- Tests: `/api/*`, SSE and the telemetry proxy are not shadowed. A deep link with `Accept: text/html`
  returns `index.html`. A missing asset returns 404, and so does a POST to an unknown path.
- `Dockerfile.ui` already copies `frontend/dist` (the plan's `web/dist`). Document it in the developer
  guide (`docs/dev/architecture.md`).

### G11 · Temporal replaces ARQ; Langfuse removed (change 1)

- **Deps:** add `pydantic-ai-slim[temporal]` (`temporalio>=1.27`), remove `arq`, and don't add
  `langfuse`.
- **Settings:** add `TEMPORAL__HOST=localhost:7233`, `TEMPORAL__NAMESPACE=default` and
  `TEMPORAL__TASK_QUEUE=draftpilot`. `core/queue/` becomes `core/temporal.py` (a lazy client getter
  plus close, wired into the lifespan). Drop the `QUEUE__` group and the
  `OTEL__LANGFUSE_*` fields; `OTEL__ENABLED` defaults to `false`.
- **Compose:** drop the six Langfuse containers (langfuse, langfuse-worker, clickhouse, minio, the
  Langfuse redis and postgres), the `LANGFUSE_*` env and the OTLP basic-auth header. Add a
  `temporal` service (`temporalio/temporal server start-dev`, SQLite on a volume, UI :8233; check the
  image and flags locally). Add `grafana/otel-lgtm` under the `observability` profile. Update
  CLAUDE.md/AGENTS.md (telemetry, queue), `.env.example`, the `run-stack` skill, and
  `src/draftpilot/worker/CLAUDE.md`. Rebuild the images before `up -d`, because the settings change.
- **Worker:** `python -m draftpilot.worker` runs a Temporal worker with
  `plugins=[PydanticAIPlugin(), LogfirePlugin()]`, replacing `worker/settings.py`'s `WorkerSettings`.
- **Agents** (`agents/runtime.py`): `Agent(name=<role>, capabilities=[TemporalDurability(...)])` for
  all 13 role specs. Toolsets are fixed when the agent is built, and the internal MCP toolset gets an
  `id`. Deps (`agents/deps.py`) become serializable: pass ids, and let activities open their own DB
  sessions.
- **Workflows:** port the eight `pydantic_graph` workflows in `agents/workflows.py` to
  `PydanticAIWorkflow` classes that declare `__pydantic_ai_agents__`. Human gates use
  `@workflow.update`/`@workflow.signal`, progress (the live trail) uses `@workflow.query`, and the
  audience-panel and brainstorm fan-outs use `asyncio.gather`. Drop `pydantic_graph` from durable
  orchestration. The non-LLM ARQ jobs become workflows too: PDF import, `reindex_project`/RAG
  index and delete, `refresh_story_twin` and `purge_rag_project`. `push_langfuse_scores` is deleted.
- **Chat:** each room thread is a long-running workflow. Tokens stream via `event_stream_topic` +
  `stream_agent_events` → the Vercel adapter encoder → SSE. Verify that this matches today's
  `useChat` stream (the old M7, now `agents/chat.py`).
- **Data:** `WorkflowRun` (and any job rows) become thin read-only copy tables keyed by Temporal
  workflow id; the retry/resume/cancel logic in `worker/functions.py` goes to Temporal. Metrics,
  feedback and online-eval results stay in Postgres only (`core/usefulness.py` drops the Langfuse
  push). This needs a reviewed migration.
- **Tests:** Tier 0 uses `WorkflowEnvironment.start_time_skipping()`. Replayer tests run over
  `tests/temporal_histories/` to catch determinism breaks. **SDLC rule:** any workflow edit must pass
  the replay tests. Add the rule to CLAUDE.md/AGENTS.md when G11 lands. Re-run every room eval
  suite on LM Studio against `evals/baselines/` (agents and workflows change).

### G12 · Frontend telemetry (change 3)

- `@pydantic/logfire-browser` with `logfire.configure()` (not `configureFrontend`); check it against
  <https://pydantic.dev/docs/logfire/instrument/typescript/get-started/>. `serviceName`
  `draftpilot-web`, `serviceVersion` from the build, and the environment and enabled flag from
  `/api/system/info`. The SDK is not loaded when telemetry is disabled.
- `traceUrl` `/api/telemetry/v1/traces` (plus metrics) is a same-origin FastAPI proxy. It forwards
  OTLP to `OTEL__EXPORTER_OTLP_ENDPOINT` (optionally otel-lgtm), applies auth and size/rate limits,
  and returns a 204 no-op when telemetry is off.
- Auto-instrumentations on: document load, fetch/XHR with `traceparent` to `/api` and `/mcp`, and
  user interaction. Also resourceTiming summary, Web Vitals, `rum.session`, errorFingerprinting and
  a React ErrorBoundary.
- Manual spans: editor load, autosave, conflicts (409), SSE reconnect, chat time to first token and
  total, suggestion accept/reject, workflow start and human-gate resolve, command palette, theme
  switch.
- Privacy: scrubbing on, URL query and fragment stripped, never script or prompt text (ids and
  lengths only), replay off, and a "Send diagnostics" toggle in settings.
- Tests: Vitest with an in-memory span processor (spans present, no text); Playwright checks that a
  UI action and its `/api` call share a trace id; pytest for the proxy.
- Because M1–M10 have already shipped, the bootstrap, proxy, ErrorBoundary, Web Vitals and all the
  manual spans above land together in G12. The old M11 part follows: the docs, plus a "slowest
  interactions" panel on `/insights`.

### G13 · Monty code mode (change 2, M8b)

- **Deps:** `pydantic-monty>=1,<2` (1.0.0 is installed) and
  `pydantic-ai-harness[code-mode,dynamic-workflow,temporal]`. Check the `CodeMode` and
  `DynamicWorkflow` signatures locally. Reconcile with the existing `core/monty.py` sandbox
  rather than keeping two.
- **CodeMode** for the Showrunner, Researcher, Continuity Supervisor, Story Editor and Twin Keeper:
  one snippet over the read-only MCP tools instead of many tool calls. Twin Keeper is currently
  deterministic extraction (`core/twins.py`), not a role spec, so it needs a spec first.
- **`analyze_script(code)`** is a read-only sandbox tool, available in-app and via MCP (gated by
  `MCP__ENABLE_CODE_TOOLS`). It runs over `ScreenplayDoc` and the Story twin, exposed as allow-listed
  `ClassInstance` host objects. It returns exact stats: dialogue share, pacing curves, and
  scene/character matrices.
- **Continuity rules as code** over story facts and timeline events. There are no `StoryFact` or
  `TimelineEvent` tables; the Story twin lives in the knowledge graph, so the rules run over typed
  `KnowledgeNode` views, per the G6 decision not to add parallel tables.
- **DynamicWorkflow** for ad-hoc interactive plans. Inside a durable run it executes inside an
  activity, never in workflow code.
- **Guardrails:** no writes (edits still go through `propose_*` → proposals). Limits come from
  `MONTY__TIMEOUT_S`, `MONTY__MAX_MEMORY_MB` and `MONTY__POOL_SIZE`. Every run gets a Logfire span
  and an `AgentRun` row.
- **Tests:** sandbox escape and limit tests, plus known Big Fish stats (Tier 0). A CodeMode vs plain
  tool-calling eval on LM Studio compares accuracy, tool calls and duration (Tier 2).
- **Docs:** user guide "Temporal UI & traces" and "Code mode"; developer guide "Durable workflows
  (Temporal)" (determinism and replay) and "Monty sandbox" (extends `docs/monty.md`).
