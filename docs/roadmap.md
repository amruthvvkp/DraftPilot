# Modernization roadmap

The source of truth for DraftPilot's phased evolution into an ultra-modern,
FinalDraft-inspired, agent-native screenwriting studio. Consult this when planning or
picking up feature work, and update each phase's status as it lands.

Tracking epic: [#13](https://github.com/amruthvvkp/DraftPilot/issues/13).

## Locked decisions

- **Look** — neutral white / dark-grey shell; retain the clapperboard amber (`#e0a458`) as
  the single accent.
- **Import/export** — built on [`screenplay-tools`](https://github.com/wildwinter/screenplay-tools)
  (MIT). `trelby` is **GPLv2+** and is used as inspiration only — never vendored. PDF export
  uses the local ReportLab renderer and HTML export uses a self-contained safe renderer.
- **Data** — the database is the structured ground truth: deeply-nested Pydantic models,
  revisioned at the scene level. Import/export translates through that ground truth.
- **Agent code execution** — model-written glue code runs through Pydantic Monty behind a
  feature flag, with explicit host functions, resource limits, audit records, and no ambient
  filesystem, environment, network, or process access. Monty is experimental and is not a
  replacement for a full sandbox when users need third-party Python packages.
- **Agent context** — instructions are layered and overridable: installation defaults, project
  instructions, artifact/outline/timeline instructions, scene instructions, and run/task
  instructions. Creative context is first-class structured data, not only prompt text.
- **Assistant presence** — the Copilot conversation and agent rail is a persistent right-side
  surface on every workflow page. Each turn is scoped to the current artifact/selection and can
  propose a typed change, ask a question, or advance a workflow decision; it never silently edits.
- **Retrieval** — Compose includes a replaceable local-first RAG service for project-scoped
  retrieval over artifacts, screenplay chunks, references, and knowledge-graph edges. Approved
  changes trigger incremental re-indexing and visible citation refresh.
- **MCP interoperability** — DraftPilot is both an MCP client and an MCP server. Built-in agents
  and external MCP-capable clients use the same typed capability service; the UI selects a
  page-aware capability bundle, while the server remains authoritative for project scope,
  permissions, approvals, redaction, and audit.

## Ground-test screenplay benchmark

The first serious validation project is a writer-owned 165-page feature screenplay developed in
Final Draft 13. It is tested through two deliberately separate tracks:

1. **From-scratch redevelopment** — provide only the premise, constraints, intended audience,
   genre, and high-level creative goals. Do not provide the existing screenplay text. DraftPilot
   must produce the brief, canon, outline, timeline, creative context, scenes, screenplay, and
   review passes through the intended workflow.
2. **Import and compare** — import the original FDX into an immutable control project, validate
   structure and formatting, run analysis/context workflows, create changes only in revisions,
   and export for round-trip comparison with the Final Draft source.

Both tracks use isolated projects and named snapshots. The control screenplay is never modified.
Evaluation records compare story beats, character arcs, pacing, tone, visual language, continuity,
format fidelity, export fidelity, and writer usefulness. This benchmark becomes a release gate
for the editor, context-generation workflows, agent permissions, revision/rollback behavior, and
FDX import/export rather than relying only on synthetic fixtures.
The fixture-safe `draftpilot.core.benchmark` contract and `scripts/benchmark_compare.py` compare
machine-readable control/candidate manifests for structure, scene order, element counts, runtime,
and multilingual metadata. They hash source bytes without embedding screenplay text and accept
isolated JSON fixtures, so the writer-owned source can be added later without coupling benchmark
execution to the live Compose database.

## Implementation checkpoint — 2026-09-04

The React/Vite studio now covers the project vault, multilingual creation flow, and typed repeatable
creative references, local artwork uploads, screenplay
workspace, semantic editor blocks, dialogue translations, revisions, timeline proposals, durable
Copilot turns, evaluations, typed agent proposals, creative-context nodes and relationships,
project-scoped RAG retrieval, MCP prompts/resources/tools, provider settings, exports, and backups.
The browser suite runs in the pinned `e2e` Playwright Compose service with mocked API responses and
no test writes to the developer database. PDF imports preserve binary bytes at the React boundary,
FDX export is exposed in the workspace, and the API rejects a primary screenplay language reused as
a dialogue-translation target. Timeline act and character lanes and editable graph relationships are
now visible in the React workflow surfaces. Pending timeline proposals reload after a browser
disconnect, and approval invalidates downstream artifacts. New projects atomically receive a feature screenplay and
Act One so the creation journey opens on a writable document. Project references now have scoped,
versioned REST mutations and a single Alembic migration head. The React story studio can now create
dependency-linked artifacts, and the portable browser suite covers reference editing. The
editor can now submit semantic block-format proposals to the Copilot approval rail with a
server-derived scene version and rollback path. Timeline proposals can also be rolled back after
approval when their expected order is still current. Typed story operations now cover loglines,
causal beats, character arcs, and canon rules through one shared REST/MCP service with versioning,
stale propagation, and RAG refresh. Phases A, B, C, D, E, and F are complete, with ongoing benchmark validation.
Context-generation workflow contracts now cover reference scenes, visual language, camera, lighting,
palettes, film/director/style research, and continuity as durable, citation-bearing, review-only
runs; see `docs/context-workflows.md`. Reviewed context suggestions can now be explicitly applied
as provenance-linked typed graph nodes with source-version checks. The portable browser suite now
includes a single broader end-to-end smoke journey covering project creation, story artifacts,
screenplay writing, translation, timeline proposal approval/rollback, agent proposal
approval/rollback, exports, backup, and non-destructive restore. Live external MCP client validation
now passes through `scripts/mcp_smoke.py` (authenticated discovery plus project-scoped resource and
typed-tool reads). Monty executions now have project-scoped redacted audit records with code hashes
and bounded telemetry fields. Translation writes now enforce configured dialogue targets and reject
the primary screenplay language across REST and MCP; continue with broader production hardening and external-client
compatibility checks. Local MCP stdio now resolves a configurable `MCP__STDIO_CLIENT_ID` through
the same project grant and audit boundary as HTTP clients. Copilot proposal creation now enforces the originating run permission mode
server-side. Durable workflow runs now persist bounded attempt counters: provider or worker
failures return the same run to `queued`, re-enqueue it until its budget is exhausted, and preserve
cancellation and worker-restart recovery. Scoped-edit proposals now require a server-defined
target envelope on both creation and approval; project-edit remains project-wide. The portable
browser gate and authenticated local Langfuse trace verification are release checks, not substitutes
for those remaining workflows.

## Phases

Phases are dependency-ordered. Each gets its own spec → implementation; A+B ship together
as the first slice.

### Phase A — App shell · [#14](https://github.com/amruthvvkp/DraftPilot/issues/14) · status: completed
Neutral theme repalette (amber accent), FinalDraft-style `/projects` vault landing
(cards + empty states), restyled collapsible left panel, top-right user menu with
Profile/Settings popups (persisted to `draftpilot_writer_profile` in local storage), `docs/references.md`
+ this roadmap, CLAUDE.md references + roadmap rules, design-system showcase updates.

### Phase B — Data backbone · [#14](https://github.com/amruthvvkp/DraftPilot/issues/14) · status: completed
`Screenplay → Act → Scene → Block` SQLModel hierarchy; `BlockType` enum (action, character,
dialogue, parenthetical, transition, lyric, note, section, synopsis, shot, page_break);
dialogue extras (dual dialogue + per-line translation); rich project metadata (description,
story outline, visual style, camera type, screening type, artwork, `genres[]`,
`languages[]`, `primary_language`); typed repeatable `ProjectReference`; nested Pydantic `ScreenplayDoc`
ground-truth with Fountain/FDX adapters; `SceneRevision` snapshot/restore; CRUD + Alembic
migration with data backfill.

### Phase C — Project-creation wizard · [#15](https://github.com/amruthvvkp/DraftPilot/issues/15) · status: completed
Multi-step New-Project popup (title, description, all supported genres, primary screenplay
language, dialogue-translation languages multi-select including Indian languages, story
outline, visual style, camera type, screening type, typed references — add multiple);
artwork upload or weblink render; navigate to the opened project on create; clickable
project cards on `/projects`. Depends on B.

### Phase D — Editor workspace · [#16](https://github.com/amruthvvkp/DraftPilot/issues/16) · status: completed
3-pane editor — left Navigator (scenes), center script (element-typed, screenplay fonts,
top element selector + bottom bold/italic/underline/color toolbar), right persistent Copilot and
agent panel. The same assistant panel appears in project, outline, timeline, context, review, and
settings workflow views.
Each scene shows an estimated duration beside cumulative start/end offsets, while the overall
runtime and pacing drift remain visible as the screenplay grows. The editor provides semantic
autocomplete, Tab-to-next-element transitions, and paired dual dialogue.
Add a Final Draft–style timeline board with a time ruler, act and character lanes, draggable scene
cards, keyboard reorder fallback, and a reversible reorder proposal that recalculates screenplay
order and dependent runtime offsets.
Beat-board drag-drop (NiceGUI trello example) with timeline/act view toggle; per-section
context refs (camera, palette, location, characters, reference scenes, directors, films,
styles, lighting plans, and color palettes); smart typing; dual + translated dialogue editing;
timeline scrubber dropdown. Add project and scene instruction editors with clear inheritance and
override indicators. Project and scene context are opened through two explicit controls; AI
formatting produces a diff proposal before application. Wires when `SceneRevision` snapshots fire.
Depends on B + C.

### Phase E — Agentic layer · [#17](https://github.com/amruthvvkp/DraftPilot/issues/17) · status: completed
Provider-agnostic PydanticAI model construction now supports OpenAI-compatible first-party,
OpenRouter/gateway, Ollama, and LM Studio endpoints; agent roles (researcher,
script assistant, associate director, audience evaluator); model switching in the agent
panel; settings provider config; MCP tools exposing project actions to external clients;
agent-assisted new-screenplay wizard (outline / genre / characters / audience / format /
length). Add reusable context-generation workflows for reference scenes, visual language,
camera, lighting, color palettes, film/director/style research, and continuity. Every workflow
must declare its input artifact scope, instruction layers, output artifact type, evaluator,
permission mode, and rollback behavior. Expose only typed DraftPilot capabilities through MCP;
route Copilot turns to the tools appropriate for the current page, artifact, and selection, and
show those active tools to the writer;
publish the same capability catalog to external clients through MCP: discoverable prompts for
workflow turns, resources for canonical artifacts/citations/schema, and tools for approved
story operations, retrieval, evaluations, exports, and run control. Support authenticated
Streamable HTTP and local stdio transports, per-client/project grants, explicit consent for
mutations, and compatibility with external clients such as Claude, ChatGPT, Gemini, and other
MCP-capable applications without duplicating business logic;
when a run needs generated code to compose or filter those capabilities, execute it through
the Monty adapter rather than an unrestricted shell or Python subprocess. Fountain, FDX, and a
best-effort ReportLab PDF and safe self-contained HTML exports now fold in here. Depends on B + D.

The guided interaction is turn-based: the user states or confirms a decision, the Copilot retrieves
relevant project context and proposes the next artifact or change, agents can collaborate through
MCP, and the UI renders persisted results as they arrive. Users can move backward to revise a
logline, character, beat, timeline event, or scene; dependent artifacts become visibly stale and
can be regenerated rather than being silently overwritten.

### Phase F — Durable agent execution and capability security · [#17](https://github.com/amruthvvkp/DraftPilot/issues/17) · status: completed
Project backup archives and non-destructive restore endpoints now protect project metadata,
references, artifacts, and canonical screenplay documents with atomic writes and checksums. The
same typed backup create/restore operations are approval-gated and available through MCP.
Persist workflows, runs, tasks, instruction resolution, context artifacts, approvals, Monty
execution records, MCP client registrations, capability discovery, prompt/resource/tool
invocations, evaluator results, and reversible change sets. Support
resumable snapshots, cancellation, bounded retries, per-tool grants, SSRF protection, output
limits, and conflict-aware application of story operations. Monty host functions are narrow,
typed adapters over DraftPilot services; filesystem, network, command, and destructive access
remain separate grants and are never implied by an agent's edit permission.

The default Compose profile also includes a local-first RAG subsystem: an indexing/retrieval API,
an asynchronous indexing worker, a replaceable vector store, and an embedding adapter that can
use a local model or a configured provider. It indexes approved project artifacts, screenplay
blocks, references, instructions, and knowledge-graph edges with project/permission boundaries;
each result carries source citations and a content version. The editor and Copilot consume this
through typed services/MCP rather than talking directly to the vector store, so the stack can
change providers without changing workflow UX.
