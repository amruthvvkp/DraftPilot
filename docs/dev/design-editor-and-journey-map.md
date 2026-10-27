# Design: single-document editor and character journey map

!!! info "Status"
    Agreed 2026-10-27; see [Decisions](#decisions). The work is tracked in the epic and issues listed
    in [Delivery](#delivery), under the v1.2 milestone. Part 1 is built behind *Settings → Editor:
    Document* (#54, #56); Part 2 is not built yet.

Two changes make DraftPilot easier to use without agents, while keeping it agent-first:

1. **A single-document script editor.** You write the screenplay as one continuous page, the way
   you would in Final Draft, with the outline folded inline.
2. **A character journey map.** A visual canvas of each character's moments, where their paths
   cross, and how the emotion rises and falls. You can drag moments to try different narrative
   orders.

Both rest on the typed story data from G14 and on the proposal model. Agents still never write
silently: everything they suggest arrives as something you accept or reject.

## Goals and non-goals

**Goals**

- Writing a scene by hand feels natural: type, and Tab and Enter pick the next element.
- The outline (acts, beats) sits beside the words it describes instead of on another page.
- Agent suggestions appear in place, as tracked changes in the page or as moved cards on the map.
- You can see which characters meet, where, and with what emotional charge, and rearrange the
  telling without changing what happened.

**Non-goals for this round**

- Real-time co-editing with cursors (CRDT/Yjs). Live sync stays per-scene; see
  [Conflicts](#live-sync-and-conflicts).
- Replacing the screenplay data model. Blocks, scenes and acts stay as they are.
- Print-accurate pagination. The paginated view stays an estimate, as today.

## Part 1 · The single-document editor

### Where we are

The Script workspace (`frontend/src/Workspace.tsx`) renders every block as its own `<textarea>`
(`script/BlockRow.tsx`), with a type dropdown, move and delete buttons, and an authorship chip.
That keeps the code simple, but it doesn't feel like writing:

- **Selecting and moving text:** you can't select across blocks or move the cursor from one to the
  next with the arrow keys. Tab is a custom handler that focuses the next textarea.
- **Formatting:** it shows as raw Fountain markup (`**bold**`). Inline formatting is issue #49.
- **The outline is elsewhere:** it lives on its own page (the Outline page), away from the scenes.
- **Saving:** every block save is a separate `PATCH` against the scene version (`If-Match`). Each
  write bumps `scene.version` and then calls `scene_changed`, which re-indexes the scene for
  retrieval, publishes `scene.changed` and asks for a Story-twin refresh (`core/scene_sync.py`).
  Writes inside one scene therefore have to go one at a time.

### The editor

One ProseMirror document per draft, built with **TipTap** (MIT; use only the open-source
extensions, not TipTap Pro):

```text
doc
└─ act            (heading: the act title; collapsible)
   ├─ beatNote    (the beat's title and summary, tinted; collapsible; not part of the script)
   └─ scene       (attrs: scene_id, version)
      ├─ sceneHeading      (INT. HOME LIBRARY - DAY)
      └─ element*          (attrs: block_id, element_type, origin, is_dual, dual_group)
         text with marks: bold, italic, underline, colour
```

- **One node per block.** Every `element` carries its `block_id`. Ids must survive editing, because
  authorship (`origin`), dialogue translations, proposals and revision restore all point at them.
  Splitting a paragraph keeps the id on the first half, and the second half is a new block.
  Merging two paragraphs keeps the first one's id and deletes the second block.
- **Marks are stored as Fountain markup.** The editor parses `**…**`, `*…*`, `_…_` and the amber mark
  (`[[color:…]]`) into marks, and serialises them back when it saves. Import, export, retrieval and
  agents keep seeing the same text, so nothing on the server changes.
- **Typing rules** follow Final Draft's habits and reuse `smartTyping.ts`:

  | Key | In | Gives |
  |---|---|---|
  | Enter | action | a new action |
  | Enter | character | dialogue |
  | Enter | dialogue | action (twice: character) |
  | Tab | action | character |
  | Tab | dialogue | parenthetical |
  | Tab | character | transition |
  | ⌘1–⌘9 | any | set the element type |

  The existing smart typing still retypes an action line when it's unambiguous (`CUT TO:`,
  `EDWARD`, `(beat)`).
- **Interface:**
  - A floating toolbar appears on selection: undo/redo, element type (*Aa*), bold, italic,
    underline, strike, colour.
  - The navigator and the context rail collapse to icons, so the page can take the full width.
  - The title page is an editable card at the top.
- **Outline inline:**
  - Acts and beats from `StoryBeat` show as tinted, non-script headings above the scenes they
    link to, using `scene_ids`.
  - Editing a beat's title or summary there saves the `StoryBeat` row with `If-Match`.
  - A toggle hides the outline for a clean read.
  - Beats with no scene yet show as placeholders with **Create scene from beat**.

### Saving: one batched write per scene

Every keystroke must not become a request. The editor keeps a dirty set of scenes, and about a
second after you stop typing it sends each dirty scene once:

```http
PUT /api/v1/projects/{id}/scenes/{scene_id}/content
If-Match: <scene version>

{ "heading": "INT. HOME LIBRARY - DAY",
  "blocks": [ {"id": 20, "element_type": "action", "text": "…"},
              {"element_type": "dialogue", "text": "…"} ] }
```

The server diffs this against the stored blocks in one transaction: it updates rows that keep their
`id`, creates rows without one, deletes missing ones, and renumbers. It bumps `version` once and
calls `scene_changed` once. It reuses `structure.py`'s block helpers, and an edited block's `origin`
becomes `human`, as today. The response returns the new version and the ids of any new blocks, so
the editor can write those ids into its nodes.

This adds one REST route, so `PARITY` in `tests/test_mcp_studio.py` needs either an MCP tool
(`write_scene` already writes a whole scene from Fountain; the new route could back it) or an
exemption.

### Agent suggestions in the page

Screenplay proposals already describe changes to specific blocks, or a whole scene as Fountain
(`propose_screenplay_change`). The editor shows a pending proposal as **decorations** on the blocks
it would change: insertions underlined, deletions struck through, and the agent role in the margin.
**Accept** and **Reject** call the existing approve and reject endpoints, and **Roll back** stays on
approved changes. Nothing in the document changes until you accept, so the same review rules apply.

Chat focus gets sharper as well. The dock's "selection" today is the selected scene. The editor can
send the selected text and its block ids, so "punch up these two lines" knows exactly which lines
you mean.

### Live sync and conflicts

When `scene.changed` arrives for a scene:

- **Not dirty locally:** replace that scene's nodes, keeping the cursor if it's elsewhere.
- **Dirty locally:** keep your text and show a bar on the scene, *Changed elsewhere: Keep mine /
  Load theirs*. This is the same pattern as the Storyline page's **Save my version / Discard my
  edits**.
- **A 409 on save** (a stale version) shows the same bar.

Real-time co-editing (Yjs) can come later without changing the document schema.

### Rollout

1. Build the batched content endpoint and its tests first. The current editor can use it too.
2. Ship the new editor behind a per-writer setting (*Settings → Editor: Classic / Document*), with
   Classic as the default.
3. Port the e2e journeys. They select controls by name: `Edit action`, `Edit dialogue`, `Format
   action` and `Edit scene heading` appear in `test_workspace.py`, `test_smoke_journey.py`,
   `test_real_stack.py` and `test_manual_journey.py`. Give the new editor accessible equivalents
   (for example, each element as a `textbox` named by its type and position).
4. Make Document the default once the journeys pass on both editors. Remove Classic one release
   later.

This supersedes #49 (rich-text editing): marks come with the editor. It also gives #51 (dual
dialogue) a natural home, as a "pair with previous dialogue" action on a dialogue element.

### Testing

- **Vitest:** the Fountain↔document round trip (every element type, marks, dual dialogue); ids
  surviving split, merge, paste and undo; the typing-rules table.
- **Python:** the content endpoint (diff semantics, one version bump, origin, 409 on a stale
  version, translations kept on surviving ids).
- **Playwright:** write a scene with the keyboard only; accept an inline agent proposal; resolve a
  conflict from a second tab.

## Part 2 · The character journey map

### Where we are

- **Timeline events** (`CharacterTimelineEvent`) belong to **one** character. They carry `position`,
  a free-text `story_time` ("1973", "Day 3, night"), a title, description, objective, emotional
  state, and optional `scene_id` and `beat_id`.
- **Beats** (`StoryBeat`) carry `character_ids` and `scene_ids`, so we can already tell which
  characters share a beat.
- **Relationships** (`CharacterRelationship`) give a relation and description between two
  characters.
- **The timeline board** (`Timeline.tsx`) reorders *scenes* by drag or keyboard as a reversible
  proposal. It shows act lanes and character lanes derived from dialogue cues.

**What's missing:**

- **Shared moments:** two characters can't share one moment.
- **A time axis:** `story_time` is text, so it can't be placed on an axis.
- **Fields:** there's no motivation, history or intensity field.
- **Two orders:** nothing separates *when it happens* from *when we see it*.

### The model: chronology vs narrative order

The map rests on one storytelling distinction:

- **Chronology** is when a moment happens in the story world.
- **Narrative order** is when the audience sees it.

They differ whenever you use a flashback, a cold open or intercutting. Dragging a card on the map
changes **only the narrative order**, so you can try different ways of telling the story without
breaking what happened.

### Data changes (one reviewed migration)

**`CharacterTimelineEvent` gains:**

| Field | Type | Purpose |
|---|---|---|
| `motivation` | text | why they act here (the objective is *what* they want) |
| `history` | text | the backstory this moment draws on |
| `intensity` | int −5…+5, default 0 | the emotional charge, drawn as a curve |
| `chrono_index` | float, nullable | a sortable position on the story-world axis; `story_time` stays as its label |

**New `StoryMoment` table:** a moment several characters share.

- Its fields are `project_id`, `title`, `summary`, `chrono_index`, `story_time`, `scene_id`,
  `beat_id` and `version`.
- Each participating character's `CharacterTimelineEvent` gets a nullable `moment_id`.
- The moment holds what happened; each character's event holds their own objective, motivation and
  emotional state in it.
- This is what draws the crossing points.

**Narrative order comes from what already exists:** a moment linked to a scene uses the scene order,
and one linked to a beat uses the beat order. Moments with neither (unplaced ideas) sit in an
*Unplaced* tray. That way the map and the script never disagree.

The backfill is cheap: existing events get `intensity = 0`, and `chrono_index` comes from
`position`. Events that share a beat or scene stay separate; the map offers **Merge into a shared
moment** rather than guessing.

### The views

One page, **Journey map**, at `/projects/:id/journey`, next to Characters in the project stepper's
tools. Its rows are characters in swimlanes (*the cast in the room's order, drag to reorder*), and
its columns switch between two axes:

| Axis | Columns are | Dragging a card |
|---|---|---|
| **Narrative** (default) | acts, then beats or scenes in script order | proposes a scene or beat reorder |
| **Chronology** | the `chrono_index` axis, labelled by `story_time` | changes when the moment happens (an `If-Match` edit, not a proposal) |

On the canvas:

- **Cards** show the moment title, story time, objective and emotional state, with a colour band
  for intensity. Clicking a card opens it in a side panel for editing, with links to its scene and
  beat.
- **Crossings:** a shared moment is drawn once and spans the lanes of everyone in it, with
  connectors into each lane. Relationship edges can be shown between lanes ("rival", "father of").
- **The emotional curve:** each lane can show a line of `intensity` across the axis; a cast
  overlay averages the lanes. Flat runs and missing lows show at a glance.
- **Scrubbing:** in Narrative order, a strip at the top is the script itself (scene numbers and
  runtime from the timeline board). Hovering a scene highlights its cards.
- **Accessibility:** every drag has a keyboard equivalent (select, then move earlier or later or to
  another act), as the Outline page does today.

Libraries: **React Flow** (`@xyflow/react`, MIT) for the canvas (pan, zoom, connectors, minimap), and
**dnd-kit** (MIT) for card dragging within lanes. Both get recorded in `docs/references.md`.

### Reordering safely

A drag in Narrative order doesn't move scenes at once. It creates the same reversible **timeline
reorder proposal** the timeline board uses today, reusing `core/timeline_proposals.py`. The map
shows the new order as a ghost until you **Apply** it, and **Roll back** stays available. For beats,
it's a direct `PATCH /beats/{id}` of `act_id` and `position`, as the Outline page does today (beats
are planning, not script text). To try several orders, **Save as
variant** stores a named narrative order without applying it. Variants are a small table:
`project_id`, `name`, ordered scene ids.

### Agents on the map

- **Chat sees the map:** with the map as the chat focus, the room knows which card or lane you've
  selected.
  - "Move the confrontation before the funeral" becomes a reorder proposal shown as a ghost.
  - "Where is Will's emotional low?" highlights cards.
  - "Give Josephine a reason to be here" proposes `motivation` on her event.
- **New tools:** chat reaches the map's data through MCP tools for moments and the new event fields
  (create, update, delete, and `propose_story_change` kinds), plus `read_journey`, a compact map
  summary for agents. Each needs a capability, an entry in `PARITY` and the role tool sets
  (`READ_TOOLS` / `PROPOSE_TOOLS`).
- **A generative card:** the map gets a chat card type (a mini lane strip), registered in the chat's
  `TOOL_CARDS`.
- **`develop_story`'s timeline stage:** it writes `intensity` and `motivation`, and proposes shared
  moments where the cast meet. This changes a workflow, so it goes behind `workflow.patched(...)`,
  needs the replay tests, and needs a `cast`/timeline eval run on LM Studio.
- **An arc check:** a new analytic workflow reads the map and reports flat arcs, characters who
  never cross the protagonist, and intensity that never turns.

### Rollout

1. The migration and API: the new fields, `StoryMoment`, backups (so moments survive a restore,
   see #52), MCP tools and parity.
2. The map in **Chronology** with editing; no reordering yet.
3. **Narrative order** with reorder proposals and variants.
4. Agent tools, the chat card, the `develop_story` changes and the arc check, with evals.

The current timeline board stays until the map's Narrative view covers its scene reordering, then
the map replaces it.

### Testing

- **Python:** the migration and backfill, moment CRUD and versioning, backups including moments,
  reorder proposals from the map, MCP parity.
- **Vitest:** lane layout (crossings, unplaced tray), the keyboard reorder, the intensity curve.
- **Playwright (real stack):** add two characters, create a shared moment, see the crossing, drag a
  scene earlier, apply, roll back.
- **LM Studio:** the `cast` suite and a new `journey` suite (sensible intensities, shared moments
  for scenes the cast share).

## Later: more visual tools

These all read the same data, so they're cheap once the map exists:

- **Tension curve** across the whole script (the cast average plus the beats' `beat_type`
  milestones).
- **Relationship graph** of the cast, with edge strength from shared moments.
- **Index cards / corkboard** over beats, for people who think on cards.
- **Structure templates** (Save the Cat, Hero's Journey, five acts) laid over the outline as target
  beats.
- **Pacing heatmap:** scene runtime against intensity, act by act.

## Delivery

Tracked under epic [#53](https://github.com/amruthvvkp/DraftPilot/issues/53), milestone v1.2:

| Issue | Scope | Depends on |
|---|---|---|
| [#54](https://github.com/amruthvvkp/DraftPilot/issues/54) Batched scene content endpoint | `PUT …/scenes/{id}/content`, one version bump and side effects, MCP parity | — |
| [#56](https://github.com/amruthvvkp/DraftPilot/issues/56) Single-document editor | TipTap schema, typing rules, toolbar, outline inline, inline proposals, conflicts, setting, e2e ports; closes #49, absorbs #51 | #54 |
| [#55](https://github.com/amruthvvkp/DraftPilot/issues/55) Journey map data | event fields, `StoryMoment`, backfill, backups, MCP tools | — |
| [#57](https://github.com/amruthvvkp/DraftPilot/issues/57) Journey map UI | Chronology, then Narrative order with reorder proposals and variants | #55 |
| [#58](https://github.com/amruthvvkp/DraftPilot/issues/58) Journey map agents | chat focus and card, `develop_story` timeline stage, arc check, evals | #57 |
| [#59](https://github.com/amruthvvkp/DraftPilot/issues/59) Visual tools | tension curve, relationship graph, corkboard, templates, heatmap | #55 |

The map can start right away, in parallel with the endpoint. The editor is the biggest single
piece.

## Decisions

Agreed on 2026-10-27, taking the recommendations above:

1. **Editor default:** Document replaces Classic. Classic stays behind the setting until the e2e
   journeys pass on both editors, Document then becomes the default, and Classic is removed one
   release later.
2. **Shared moments:** you create them explicitly (**Merge into a shared moment**). The Story twin
   and `develop_story` may *propose* them, as reviewable proposals, but never merge silently.
3. **Intensity scale:** a single −5…+5 valence (negative is a low, positive a high), default 0.
4. **Variants:** local to the map: a named, ordered list of scene ids that you can apply as a
   reorder proposal. Turning a variant into a full draft can come later if writers ask for it.
