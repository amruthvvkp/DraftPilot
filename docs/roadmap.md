# Modernization roadmap

The source of truth for DraftPilot's phased evolution into an ultra-modern,
FinalDraft-inspired, agent-native screenwriting studio. Consult this when planning or
picking up feature work, and update each phase's status as it lands.

Tracking epic: [#13](https://github.com/amruthvvkp/DraftPilot/issues/13).

## Locked decisions

- **Look** — neutral white / dark-grey shell; retain the clapperboard amber (`#e0a458`) as
  the single accent.
- **Import/export** — built on [`screenplay-tools`](https://github.com/wildwinter/screenplay-tools)
  (MIT). `trelby` is **GPLv2+** and is used as inspiration only — never vendored. PDF/HTML
  export (via `screenplain` + `reportlab`) is deferred to Phase E.
- **Data** — the database is the structured ground truth: deeply-nested Pydantic models,
  revisioned at the scene level. Import/export translates through that ground truth.
- **Agent code execution** — model-written glue code runs through Pydantic Monty behind a
  feature flag, with explicit host functions, resource limits, audit records, and no ambient
  filesystem, environment, network, or process access. Monty is experimental and is not a
  replacement for a full sandbox when users need third-party Python packages.
- **Agent context** — instructions are layered and overridable: installation defaults, project
  instructions, artifact/outline/timeline instructions, scene instructions, and run/task
  instructions. Creative context is first-class structured data, not only prompt text.

## Phases

Phases are dependency-ordered. Each gets its own spec → implementation; A+B ship together
as the first slice.

### Phase A — App shell · [#14](https://github.com/amruthvvkp/DraftPilot/issues/14) · status: in progress
Neutral theme repalette (amber accent), FinalDraft-style `/projects` vault landing
(cards + empty states), restyled collapsible left panel, top-right user menu with
Profile/Settings popups (persisted to `app.storage.user`; no auth yet), `docs/references.md`
+ this roadmap, CLAUDE.md references + roadmap rules, design-system showcase updates.

### Phase B — Data backbone · [#14](https://github.com/amruthvvkp/DraftPilot/issues/14) · status: in progress
`Screenplay → Act → Scene → Block` SQLModel hierarchy; `BlockType` enum (action, character,
dialogue, parenthetical, transition, lyric, note, section, synopsis, shot, page_break);
dialogue extras (dual dialogue + per-line translation); rich project metadata (description,
story outline, visual style, camera type, screening type, artwork, `genres[]`,
`languages[]`); typed repeatable `ProjectReference`; nested Pydantic `ScreenplayDoc`
ground-truth with Fountain/FDX adapters; `SceneRevision` snapshot/restore; CRUD + Alembic
migration with data backfill.

### Phase C — Project-creation wizard · [#15](https://github.com/amruthvvkp/DraftPilot/issues/15) · status: complete
Multi-step New-Project popup (title, description, genres, languages multi-select, story
outline, visual style, camera type, screening type, typed references — add multiple);
artwork upload or weblink render; navigate to the opened project on create; clickable
project cards on `/projects`. Depends on B.

### Phase D — Editor workspace · [#16](https://github.com/amruthvvkp/DraftPilot/issues/16) · status: planned
3-pane editor — left Navigator (scenes), center script (element-typed, screenplay fonts,
top element selector + bottom bold/italic/underline/color toolbar), right agent chat panel.
Beat-board drag-drop (NiceGUI trello example) with timeline/act view toggle; per-section
context refs (camera, palette, location, characters, reference scenes, directors, films,
styles, lighting plans, and color palettes); smart typing; dual + translated dialogue editing;
timeline scrubber dropdown. Add project and scene instruction editors with clear inheritance
and override indicators. Wires when `SceneRevision` snapshots fire.
Depends on B + C.

### Phase E — Agentic layer · [#17](https://github.com/amruthvvkp/DraftPilot/issues/17) · status: planned
Provider-agnostic PydanticAI across all supported providers; agent roles (researcher,
script assistant, associate director, audience evaluator); model switching in the agent
panel; settings provider config; MCP tools exposing project actions to external clients;
agent-assisted new-screenplay wizard (outline / genre / characters / audience / format /
length). Add reusable context-generation workflows for reference scenes, visual language,
camera, lighting, color palettes, film/director/style research, and continuity. Every workflow
must declare its input artifact scope, instruction layers, output artifact type, evaluator,
permission mode, and rollback behavior. Expose only typed DraftPilot capabilities through MCP;
when a run needs generated code to compose or filter those capabilities, execute it through
the Monty adapter rather than an unrestricted shell or Python subprocess. PDF/HTML export folds
in here. Depends on B + D.

### Phase F — Durable agent execution and capability security · [#17](https://github.com/amruthvvkp/DraftPilot/issues/17) · status: planned
Persist workflows, runs, tasks, instruction resolution, context artifacts, approvals, Monty
execution records, MCP tool calls, evaluator results, and reversible change sets. Support
resumable snapshots, cancellation, bounded retries, per-tool grants, SSRF protection, output
limits, and conflict-aware application of story operations. Monty host functions are narrow,
typed adapters over DraftPilot services; filesystem, network, command, and destructive access
remain separate grants and are never implied by an agent's edit permission.
