# React Screenplay Workspace Implementation Plan

## Goal

Move opened projects from the React vault into a modern screenplay workspace while keeping the
existing NiceGUI editor available during migration. Establish the data boundary needed for
scene-aware editing, layered instructions, and future creative-context workflows.

## Visual reference

Use the page wireframes in [`draftpilot-pages.html`](../wireframes/draftpilot-pages.html) as the
layout reference for the next surfaces. The existing project vault and screenplay workspace are
the visual anchors; the other views show the intended information hierarchy for project overview,
story development, agents/review, and settings/export. Every workflow view now includes the same
right-side Copilot rail: conversation history, available agents, active run state, scoped context,
and a turn input. The assistant is persistent across stage changes, not an editor-only feature.
The DraftPilot wordmark uses an amber star with an editorial serif “Draft” and precise sans-serif
“Pilot” treatment as the premium shell identity.
The editor reference also makes pacing visible: each scene carries an estimated duration and
cumulative start/end offsets. Its interaction model includes semantic autocomplete, Tab-based
element transitions, and paired dual dialogue. Project and scene context are two explicit controls
that open the same expanded instruction editor; AI formatting is previewed as a diff before it can
be applied. The Copilot rail exposes the page-aware tools available for the current artifact.

## Scope

- Add a read-only workspace API returning a project, screenplay metadata, acts, and scenes.
- Route project cards to a React workspace instead of treating a project id as a screenplay id.
- Render a three-pane workspace shell: scene navigator, screenplay canvas, and context/instructions.
- Treat scene time as a first-class screenplay property: estimated duration, cumulative start/end
  offsets, overall runtime, and pacing/readiness drift indicators.
- Add a timeline board where writers can drag scenes to refactor screenplay order. Reordering must
  recalculate scene numbers and offsets, preserve beat/character links, mark dependent artifacts
  stale, and remain a reviewable reversible proposal until approved.
- Make editor transitions semantic: autocomplete for elements, characters, and headings; Tab moves
  to the next valid element; dual dialogue is represented as a paired structure.
- Keep the screenplay's primary language authoritative for scene headings and action. Store
  translated dialogue per language as linked variants of the original dialogue block, with the
  source text preserved and translation approval/refresh state visible.
- Make project and scene context buttons open expanded instruction editors. AI formatting creates a
  typed proposal and visible diff that requires writer approval.
- Add project and scene instruction fields to the UI state without inventing persistence before
  their canonical models/API are designed.
- Use Python Playwright with intercepted API responses for browser acceptance; never use the
  developer's Compose database as test state.
- Reserve the first end-to-end screenplay benchmark for two isolated tracks: rebuild the writer's
  feature from high-level inputs without screenplay text, then import the immutable Final Draft
  13 FDX control and compare structure, fidelity, context, and revisions.
- Treat the guided workflow as a loop rather than a one-way wizard: logline → outline → character
  stories → timeline → scenes → screenplay → review, with every artifact editable and every turn
  able to send its current scoped context to the Copilot and selected agents.
- Add a local-first RAG service to Compose for indexing project artifacts, imported screenplay
  chunks, references, and knowledge-graph edges. Retrieval must be citation-bearing, project-scoped,
  refreshable after each approved change, and replaceable without coupling the editor to one vector
  database or embedding provider.
- Keep MCP as the typed capability boundary for agents. The UI subscribes to persisted run events,
  tool results, and artifact changes, then refreshes visible panels from the server rather than
  rendering hidden agent state.
- Treat MCP interoperability as a product contract: built-in DraftPilot agents and external
  clients consume the same page-aware catalog of prompts, resources, and tools. Outline pages
  expose brief/canon/beat tools; timeline pages expose scene-order/runtime tools; editor pages
  expose screenplay/context/revision tools; review pages expose evaluation/proposal tools; and
  export/settings pages expose format/provider/backup tools. Every invocation is server-scoped,
  permission-checked, approval-aware, redacted, and audited.

## Exit criteria

- A project card opens `/projects/{project_id}` and displays its screenplay workspace.
- Empty and populated scene states are legible, responsive, and keyboard navigable.
- Current project, selected scene, and instruction context are represented in the UI.
- API and browser tests pass, frontend builds, and the existing Python gates remain green.
- The benchmark contract is documented before using the real screenplay: source control project,
  from-scratch project, artifact manifests, rubric, snapshots, and comparison outputs.
- The wireframe contract shows a Copilot rail on every workflow page and a visible path from
  conversation turn to scoped artifact proposal, approval, persistence, retrieval refresh, and UI
  update. The editor reference additionally shows runtime accumulation, semantic typing aids,
  context switching, diff review, and page-aware tool routing.
