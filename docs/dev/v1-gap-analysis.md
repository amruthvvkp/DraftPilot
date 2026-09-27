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
| G9 · Docs and verification | 🟡 in progress | this commit | Zensical user guide (start, editor, story tools, room, settings, checklist), advanced guides, developer guide (architecture, standards, extending the room), a generated HTTP API reference (checked by a test), a mkdocstrings Python reference, and a strict docs build in CI. A real-stack browser smoke test on Big Fish (`-m stack`, no mocks) passes; it found and fixed a PDF export crash on apostrophes. **Open:** eval baselines for all suites |

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
