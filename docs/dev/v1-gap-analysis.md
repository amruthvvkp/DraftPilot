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
| G10 · SPA hosting | ✅ done | change 4 | `app.frontend()` replaces the custom fallback; unmatched `/api/*` GETs stay JSON 404s (the frontend fallback would otherwise return the shell to `Accept: text/html`); immutable `/assets/*`, `no-cache` shell; `WEB__REQUIRE_FRONTEND` (true in `Dockerfile.ui`, false in `compose.dev.yml`). Auth was already on the API router only. Verified live on :9000 |
| G11 · Temporal, Langfuse out | ✅ done (#32) | change 1 | Every job, run, room workflow and chat turn is a Temporal workflow served by `python -m draftpilot.worker`. Room roles are durable agents (model refs, signed MCP identity). ARQ, `pydantic_graph` orchestration and Langfuse are gone, with `otel-lgtm` available as an opt-in profile. Replay tests run over `tests/temporal_histories/`. Verified live on :9000 (jobs, runs, room workflow and cancel, streamed chat on LM Studio) |
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

#### G11 implementation design (#32)

Decisions made against pydantic-ai 2.51 / temporalio 1.33, landed as G11a–G11e (each keeps the suite green):

- **G11a · Infra.** `core/temporal.py`: a lazy `Client` with `PydanticAIPlugin`, plus
  `start_job(name, *args, id=...)`, `start_best_effort(...)` (the old `enqueue_best_effort`) and
  `start_run(run_id)`. Workflow types are started by name, so call sites barely change. Compose:
  Temporal dev server and `otel-lgtm` (`observability` profile); the six Langfuse containers go.
- **G11b · Worker and jobs.** `python -m draftpilot.worker` runs one Temporal worker. The RAG index,
  delete, reindex and purge jobs, the Story-twin refresh and screenplay analysis become one-activity
  workflows. `execute_workflow` becomes `WorkflowRunWorkflow`: copilot, context and evaluation runs
  execute as an activity whose `RetryPolicy` takes the run's `max_attempts`. `WorkflowRun` gains
  `temporal_workflow_id`. Cancelling a run cancels the workflow as well. The startup requeue and
  `_retry_or_fail` are deleted, because retrying and resuming are now Temporal's job.
- **G11c · Durable room.** There is one module-level `Agent` per role (13) with
  `TemporalDurability`, plus a `ResolveModelId` capability. It resolves the model ref carried on
  `RoomDeps` (`default` or `profile:<id>`) to a model on the worker, so the provider profile and
  LM Studio `auto` still resolve per run. The MCP toolset (`id="draftpilot"`) is fixed and filtered
  per run from `deps.permission_mode`/`deps.tools`. The worker shares toolset sessions across runs,
  so the internal-agent identity can no longer travel in a contextvar. `process_tool_call` sends it
  as HMAC-signed request `_meta` instead. The MCP server verifies the signature and binds
  `acting_as` for that call only. External clients cannot forge it, and project isolation holds
  under concurrency. `RunMeter.finish` becomes an activity, and model and provider are read from the
  response. The eight room workflows become `@workflow.defn` classes. Loops are plain Python, fan-outs
  use `asyncio.gather`, the trail is exposed as `@workflow.query` `progress` and mirrored to the
  `WorkflowRun` copy by an activity, and the reasoning-runaway fallback is kept. **Gate:** workflows
  still end by creating proposals, and the writer decides them through the proposals API. Proposals
  are already durable in Postgres, so a workflow parked on a signal for days would duplicate that
  state.
- **G11d · Chat.** Each chat turn is a short `RoomChatWorkflow` started by the API. The API relays
  `stream_agent_events` through `VercelAIAdapter`'s encoder as the same SSE `useChat` consumes
  today. It is per turn rather than one long workflow per thread, because `useChat` resends the
  history each turn and the transcript table already persists it.
- **G11e · Tests and rules.** Tier 0 uses `WorkflowEnvironment.start_time_skipping()` with
  `TestModel`/`FunctionModel`. Recorded histories live in `tests/temporal_histories/`, and a
  `Replayer` test replays them. The replay rule goes into CLAUDE.md/AGENTS.md. Room evals are re-run
  on LM Studio against the baselines.

**As built (deviations from the list above):**

- `__pydantic_ai_agents__` isn't used. All eight room workflows share a base class, and the plugin
  would register every agent's activities once per subclass, so the worker registers them once with
  `room_agent_activities()`. The agents are built at import, outside any workflow.
- Chat has its own 13 durable agents (`chat_agents()`, `chat__<role>` activities). They carry
  `event_stream_topic`, and room workflows host no event stream. Each chat turn is its own workflow,
  not one long workflow per thread, because `useChat` resends the history and the transcript table
  keeps it. The SSE relay ends only after the workflow has saved the turn, as `on_complete` did.
- Human gates stay as proposals decided through the proposals API. Proposals are durable in
  Postgres, so parking a workflow on a signal would duplicate that state.
- A room run is `execute_workflow` (prepare → child `room:<key>` → online checks). When a writer
  cancels, the child ends Canceled and the parent completes with `{"status": "cancelled"}`.
- `run_room_workflow` (evals, tests) runs the same workflow on an embedded time-skipping server.
- Tier 0 covers Temporal workflows, cancellation and streamed chat. The replay suite covers every
  workflow type except the one-activity RAG jobs.

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

## v1.0 completion (G14–G21, #37)

!!! info "Status"
    Planned 2026-10-26. Each step ends green, references its issue and is pushed.

| Step | Status | Notes |
|---|---|---|
| G14 · Typed story domain | ✅ done | `Character`, `CharacterRelationship`, `CharacterTimelineEvent`, `Location`, `StoryBeat` tables plus storyline fields (premise, synopsis, theme, tone); migration `a1b2c3d4e5f6` backfills Twin Keeper graph nodes and outline-artifact beats (Big Fish copy: 48 characters, 148 locations). One service layer (`core/story/`, `core/proposals.py`, `core/timeline_proposals.py`, `core/project_backup.py`, `core/errors.py`) shared by REST and MCP; MCP no longer imports `api.*`. Act CRUD, scene create (incl. the first scene), move and delete. Story proposals (`character`/`location`/`beat`/`timeline_event`/`relationship` create·update·delete, `storyline`, whole `outline`) apply as the writer and roll back; `character_arcs` and `notes_to_outline` now propose onto them. The Twin Keeper derives into the tables and never overwrites writer edits; the agent brief carries storyline, cast (motives, objectives, arcs, timelines), places and beats. Backups carry the story with remapped links |
| G15 · Manual studio | ✅ done | react-router 7 + TanStack Query (SSE invalidates queries; one shared EventSource per project); no full-page reloads. Project shell with the Storyline → Characters → Outline → Script stepper and completion, a Context map (the exact agent brief plus empty fields with deep links), and a chat-dock rail. New pages: Storyline (If-Match save with conflict recovery), Characters (profile, relationships, timeline editor), Locations, Outline (any number of acts, drag/keyboard beats, scene and character links, create scene from beat; replaces the beat board). Script: first-scene creation, scene move/delete, direct block-type change, real continuous view. 33 Vitest tests in 7 files; mocked e2e updated; real-stack `tests/e2e/test_manual_journey.py` (`-m stack`) |
| G17 · AG-UI chat | 🔄 backend done (`52df396`); chat dock in progress | `AGUIAdapter` over the `room:chat` workflow (patched), deferred approvals as AG-UI interrupts resolved through a signed approval probe, server-kept `ChatThread`s, frontend tools as an `ExternalToolset` |
| G18 · Agentic completeness | ✅ backend done (`438cd30`) | `room:develop_story` pipeline gated on the writer at every stage via `proposal_decided` signals; showrunner `plan` and `consult_many`; chat tool sets cover the studio by mode; `storyline` and `cast` eval suites (LM Studio run pending) |
| G19 · Packaging and release | ✅ done | Published as `draftpilot-studio` (PyPI `draftpilot` belongs to an unrelated project; module and CLI stay `draftpilot`) and `draftpilot-mcp`. Real runtime dependencies; `draftpilot` CLI (`serve`, `worker`, `migrate`, `mcp`, `rag`, `version`); migrations ship inside the package (`src/draftpilot/migrations`); the studio build ships in the wheel (`src/draftpilot/studio`, `scripts/build_release.sh`); metadata from the installed distribution. `packages/draftpilot-mcp` (uv workspace member) with its own CLI (`serve`, `trust`, `revoke`, `config`, `tools`). One multi-target `Dockerfile` (`runtime`, `dev`) for every service; `compose.release.yml` for the published image. `release.yml` (tag → PyPI trusted publishing, GHCR multi-arch, GitHub Release), docs workflow re-enabled, a package job in CI. Verified: both wheels install in a clean venv, migrate a fresh database and serve the API and the packaged studio |
| G16 · Full MCP surface | ✅ done | 70 tools, 6 prompts, 8 resource templates. New `mcp/studio_tools.py` over the shared services: projects (list/create/update/duplicate/delete, references), storyline, story entities (character, relationship, timeline event, location, beat: list/read/create/update/delete), `read_outline`, `read_story_context`, `propose_story_change`, `propose_outline`, acts, scenes (`create_scene` from Fountain, `write_scene`, move, delete), blocks, snapshots/diff/restore, `import_screenplay`, `list_proposals`, rejects, canon nodes/edges, artifacts, twins (refresh, writer twin read/profile/memory), reindex, evaluation runs; `greet` removed. Five stage prompts (`develop_storyline` … `review_script`). Installation-wide grants (`mcp_grant.project_id` NULL, migration `b2c3d4e5f6a7`, `POST /api/v1/mcp/grants` with `["*"]`) let a trusted client list and create projects; approval-required writes still need a writer-decided `approval_id`. `tests/test_mcp_studio.py`: REST↔MCP parity map (fails on an unmapped route), an end-to-end external-agent journey through approvals, and scope/grant enforcement. New REST deletes for artifacts and canon nodes. `docs/mcp.md` rewritten (connect, trust, flow, tool reference; stale `approved: true`/ARQ text fixed) |

### Context

G0–G11 are done: FastAPI host, data backbone, room on Temporal, RAG, twins, evals, docs. G11 (#32) landed in `c50d31a`. Measured against the six v1.0 goals, an audit of the code found these gaps:

- **The manual flow breaks.** A new project can't get its first scene by hand (`frontend/src/Workspace.tsx:324`). You can't edit the logline or description after the wizard. Acts are fixed at 3. Characters are scattered across artifacts, graph nodes and the twin, with no motive, objective or timeline fields. Beats don't link to scenes. Scenes, artifacts and graph nodes can't be deleted.
- **MCP is incomplete.** It has 27 tools but no create, edit or delete for projects, scenes, blocks, acts, characters or locations. It also lacks proposal reject, import, revision snapshot, restore and diff, graph writes and twin refresh, and the `greet` stub is still there. It borrows private helpers from the `api.*` modules, so it can't be split into its own package.
- **Chat isn't finished.** It uses the Vercel AI protocol (AG-UI isn't installed). There are two overlapping chat systems (`RoomChat` and the polling `CopilotPanel`). Chat isn't persisted and has no threads, generative UI or markdown. It can't create projects, artifacts or scenes, can't follow runs, and can't wait for an approval in-chat, because there are no deferred tools.
- **Agentic gaps.** Nothing chains Project → Storyline → Characters → Outline → Script, and there's no planner and no parallel specialists.
- **Packaging.** Runtime dependencies sit in uv groups, so a built wheel won't run. The CLI is a stub. `frontend/dist` and `migrations` live outside the package, and paths are found by walking up the folder tree. There is no release workflow, and `docs.yml` is disabled.
- **Tests.** End-to-end tests are almost all mocked, and there are only 2 Vitest files.

**Decisions (writer, 2026-10-26):**
- PydanticAI is the only agent framework, AG-UI included. The backend uses `pydantic_ai.ui.ag_ui.AGUIAdapter`. The frontend uses only a thin AG-UI protocol client (`@ag-ui/client` for transport and types), with no CopilotKit or other agent runtime.
- Story entities become typed tables.
- `draftpilot-mcp` is a uv workspace member that depends on the core package.
- I set up the release workflows and you push the tag.

### Step 0 · Bookkeeping

1. Run the suite, the replay tests and the lint gates (ruff, mypy, interrogate) on the staged G11 work, then commit it on `amruthvvkp/issue32` (refs #32).
2. Open a GitHub epic issue "v1.0 completion" with a child issue for each of G14–G21 (`gh`), and branch `amruthvvkp/issue<N>`.
3. Write this plan to `docs/dev/v1-gap-analysis.md`, in a new section "v1.0 completion (G14–G21)", and update `docs/roadmap.md`. Commit both before any code.

Every step below ends green (Tier 0, replay, ruff, mypy, interrogate 100%), is committed referencing its issue, and is pushed. Agent, prompt and tool changes also run their LM Studio evals.

### G14 · Typed story domain (data + core services) (#38)

- **New SQLModel tables** (`models/story.py`, crud in `crud/story.py`):
  - `Character`: name, role, logline, bio, want, need, motive, objective, flaw, arc_summary, voice, notes, version, origin.
  - `CharacterRelationship`
  - `CharacterTimelineEvent`: character, order or story time, optional scene, event, objective, emotional state.
  - `Location`
  - `StoryBeat`: act, order, title, summary, beat type, linked scene ids.
- **Storyline fields on Project:** logline, premise, synopsis, theme, tone. Make them editable through the existing `ProjectPatch`.
- **Act CRUD:** create, rename, reorder and delete, replacing the hardcoded 3 acts.
- **Alembic migration**, reviewed by hand per CLAUDE.md, plus a data backfill:
  - character artifacts and `character`/`location` graph nodes become rows;
  - outline-artifact beats become `StoryBeat`s.
- **One service layer, `core/story/`**, that both REST and MCP call. Move the helpers MCP currently borrows from `api.agent`, `api.artifacts`, `api.backups` and `api.timeline` into `core/`. Also add scene create, delete and move, and artifact and graph-node delete.
- **Agent writes stay proposals.** Add new reversible `AgentProposal` kinds: `story_entity_create` and `story_entity_update` (characters, beats, timeline events, storyline fields).
- **Twins:** the Story twin brief and the RAG index read the new tables, and the graph links to them (no parallel twin store).
- **Tests:** CRUD, versioning (409), backfill, and proposal apply and rollback.

### G15 · Manual studio (non-agentic end-to-end) (#39)

- **Router and data layer:** react-router with TanStack Query, replacing the regex routing, `location.assign` and `window.location.reload()`. Cache invalidation comes from the existing SSE `subscribeProjectEvents`.
- **A guided project shell**, shown as a stepper: **Project → Storyline → Characters → Outline → Script**, plus a "Context map" panel showing exactly what agents will see per stage, and which fields are empty.
- **Pages:**
  - **Storyline:** logline, premise, synopsis, theme and tone.
  - **Characters:** a list, a detail form (motive, objective, want/need, arc, relationships) and a per-character timeline editor.
  - **Locations.**
  - **Outline:** any number of acts; beats you can drag and link to scenes; a manual "create scenes from beats".
  - **Script:** create the first scene, delete and move scenes, and change block type directly (agents still go through proposals).
- **Tests:** Vitest component tests for the new pages and the api layer. A Playwright **real-stack** journey with no mocks: create project → storyline → 2 characters with timelines → outline → scenes → write blocks → export.

### G16 · Full MCP surface (parity with REST) (#40)

- **New tools over `core/story` and the existing services:**
  - project create, patch, duplicate and delete;
  - storyline;
  - character, location, beat, timeline event and relationship CRUD;
  - act and scene CRUD and move;
  - block create, patch, delete and reorder;
  - import (Fountain, FDX, PDF);
  - revision snapshot, restore and diff;
  - proposal reject for both kinds;
  - knowledge-graph node and edge writes;
  - story-twin refresh, writer-twin read and update;
  - artifact create and patch.
- **Remove `greet`.**
- **Write semantics:**
  - External clients write directly, and every write needs the existing argument-bound `approval_id`.
  - In-app agents get `propose_*` variants that create proposals.
  - The capability catalog gains an entry for each new capability.
- **Discoverable content:**
  - one prompt per stage (`develop_storyline`, `develop_characters`, `build_outline`, `draft_script`, `review_script`), so Claude or ChatGPT can drive the whole flow;
  - resources for characters, beats, timeline and the storyline.
- **Tests:**
  - every tool through an in-memory FastMCP `Client`;
  - one end-to-end Streamable HTTP test;
  - a **parity test** that fails when a domain REST route has no MCP tool;
  - fix `docs/mcp.md`, which is stale (`approved: true`, tool counts).

### G17 · AG-UI chat on PydanticAI (#41)

- **Backend:**
  - Add the `pydantic-ai-slim[ag-ui]` dependency.
  - In `agents/chat.py`, replace `VercelAIAdapter` with `AGUIAdapter`. The Temporal relay (`stream_agent_events` → `transform_stream`) is kept.
  - Role, mode and page context arrive in AG-UI `state` / `forwardedProps`, not in query params.
- **Threads:** a new `ChatThread` table keyed by AG-UI `threadId`, plus transcript load, new, rename and delete.
- **Human-in-the-loop:**
  - Approval-gated tools become PydanticAI deferred tools (`requires_approval` → `DeferredToolRequests`).
  - They surface as AG-UI interrupts, rendered as an approval card.
  - When the writer decides, the next turn resumes with `DeferredToolResults`.
  - This also records the `MCPApprovalRequest` decision.
- **Shared state:** the agent emits `STATE_SNAPSHOT`/`STATE_DELTA` (pipeline stage, active plan, progress), and the UI sends page context (project, scene, selection).
- **Frontend:**
  - One persistent **chat dock** in the router layout, on every page. It replaces both `RoomChat.tsx` and `CopilotPanel.tsx`; the polling is retired.
  - Markdown rendering, plus stop, retry and regenerate.
  - A **generative-UI registry** mapping tool name or result type to a React card: character card, beat list, scene diff, proposal approve/reject, workflow progress, coverage report, plan checklist.
  - Frontend tools exposed to the agent: `navigate`, `open_scene`, `highlight_block`.
- **Temporal:** changing `RoomChat` means re-recording replay histories or `workflow.patched`, per the replay rule.
- **Tests:**
  - AG-UI stream contract (event order, interrupt and resume);
  - Vitest for the event reducer and the registry;
  - Playwright for chat on the real stack, using a scripted `FunctionModel` provider profile for determinism;
  - LM Studio evals for room Q&A re-run.

### G18 · Agentic completeness (#42)

- **Chat tool sets** cover every G16 capability, by permission mode. Chat can create a project, develop the storyline, characters, timelines and outline, write scenes, start and follow workflows (`read_workflow_run`), and approve in-chat.
- **A `develop_story` pipeline workflow** (Temporal parent):
  - premise → storyline → characters (fan-out per character) → character timelines → outline (evaluator-optimizer, reusing `notes_to_outline`) → scenes (child `draft_scenes`) → coverage.
  - Each stage ends in proposals. The workflow waits on a `proposal_decided` signal, which the proposals API sends after Postgres commits (Postgres stays the source of truth). The UI shows it as a progress card.
- **Planner and swarm:**
  - The showrunner gets a typed `make_plan` output (shown as a checklist through AG-UI state).
  - Parallel `consult_many` runs specialists with `asyncio.gather`, under the shared usage budget.
  - A new `character_developer` role spec.
- **Evals:** new `pydantic_evals` suites (`develop_storyline`, `character_profile`, `pipeline_smoke`) on LM Studio, with baselines in `evals/baselines/`, plus replay histories for the new workflows.

### G19 · Packaging and release (#43)

- **uv workspace:**
  - root `draftpilot` (core, web, worker, rag);
  - `packages/draftpilot-mcp` (`src/draftpilot_mcp`), which moves the server out of `src/draftpilot/mcp`, re-exported for in-app agents, and depends on `draftpilot`.
- **Dependencies:** convert the uv groups to `[project.optional-dependencies]` extras (`web`, `worker`, `rag`, `all`), and make real runtime deps of the core.
- **CLI:** a real `draftpilot` command (`serve`, `worker`, `migrate`, `mcp`, `rag`, `version`) and `draftpilot-mcp` (stdio or http, settings via `MCP__`).
- **Package data and paths:**
  - Ship `frontend/dist` (built in CI) and `migrations/` as package data under `src/draftpilot/`.
  - Alembic is driven through `importlib.resources`.
  - Fix the path walking in `core/config.py:17` and `evals/baseline.py:10`.
- **One multi-arch image**, `ghcr.io/amruthvvkp/draftpilot`, with the command picking the role. Compose services use it. Add `compose.release.yml` pinned to the published tag, and keep `compose.dev.yml`. Fix the stale "ARQ" comment.
- **`.github/workflows/release.yml`**, triggered by a `v*` tag:
  - `uv build --all-packages` and `twine check`;
  - PyPI trusted publishing for both packages;
  - buildx push to GHCR;
  - a GitHub Release with the compose files attached.
- Re-enable `docs.yml`. Check that the PyPI names are free.
- **Checks:** install both wheels in a clean venv, run `draftpilot migrate && draftpilot serve` against compose Postgres, and confirm `uvx --from dist/draftpilot_mcp-*.whl draftpilot-mcp --help` works and that Claude Code connects over stdio.

### G20 · End-to-end verification (#44)

- The real-stack Playwright manual journey (G15) and chat journey (G17).
- Claude Code connected to the `draftpilot-mcp` stdio server develops a short screenplay end to end, using only MCP tools and prompts. Record it as `scripts/mcp_journey.py`, a smoke check you can run.
- `develop_story` on LM Studio against Big Fish-style premise inputs.
- Rebuild the images after the settings changes. Never tear the stack down (hot reload).

### G21 · Docs (#45)

- User guide: the guided flow, chat and generative cards, in-chat approvals, threads.
- `docs/mcp.md`: full tool and prompt reference, plus connecting Claude Desktop, Claude Code and ChatGPT.
- New `docs/install.md`: pip and uvx, Docker image, compose stack.
- Developer guide: AG-UI, the pipeline workflow, the workspace layout and how to release.
- Update CLAUDE.md, AGENTS.md, the `.claude` skills and `docs/references.md` (AG-UI).

### Order

G14 → G15 and G16 (independent once G14 is in) → G17 → G18 → G19 → G20 → G21. G19's workspace split comes after G16, so the MCP move happens once. I'll ask before any outward step beyond pushing branches: no PyPI or GHCR push, and no release tag.

### Verification (each step and final)

- `uv run pytest tests --ignore=tests/e2e` and `uv run pytest tests/test_temporal_replay.py`
- `uv run ruff check src migrations packages`, `uv run mypy src packages`, `uv run interrogate src migrations packages`
- `npm --prefix frontend run test && npm --prefix frontend run build`
- `uv run pytest tests/e2e` and `-m stack` against :9000
- `uv run pytest -m lmstudio` and `uv run python -m draftpilot.evals <suite>` against the baselines
- `uv build --all-packages`, then a clean-venv install smoke and `docker build` of the image
