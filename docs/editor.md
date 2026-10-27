# Writing in the studio

The workspace has three columns:

- on the left, the **navigator**: your scenes with their estimated runtime, and a pacing gauge
  against the format's target length;
- in the middle, the **page**;
- on the right, the **context rail** (instructions, translations, snapshots, creative context and
  **External agent approvals**) and the **chat** with the room ([Chat with the room](chat.md)).

Requests from an external agent over MCP that need your approval wait under **External agent
approvals**: **Approve request** or **Reject** each one (see [MCP integration](mcp.md)).

## Screenplay elements

Every line of a scene is a typed block: action, character, dialogue, parenthetical, transition,
shot, page break, and so on. The type sits to the left of each block.

- ++tab++ moves to the next block.
- Character names autocomplete from the cast you've already written, and character cues upper-case as
  you type.
- **Smart typing** retypes an action block when you leave it, but only when it's unambiguous:
  - an all-caps name such as `EDWARD` or `WILL (V.O.)` becomes a character cue;
  - a line such as `(beat)` becomes a parenthetical;
  - `CUT TO:` or `FADE OUT.` becomes a transition.
- To change a block's type, pick a new one from the type next to the block. The change saves at
  once, like a text edit.
- **＋ Add element** under the page adds a block of any type at the end of the scene.
- Hover over a block, or focus it, to reveal its tools: move it up or down, delete it, and see who
  last wrote it. The authorship chip reads *agent* once an approved proposal wrote the block, and it
  disappears after you edit the block yourself.

The formatting toolbar above the page wraps the selected text in **bold**, *italic*, underline or an
amber mark. These are stored as Fountain markup (`**bold**`, `*italic*`, `_underline_`), shown as
you typed them, and exported as-is.

## Scenes

- A draft with no scenes shows **Your first scene starts here.** Type a heading such as
  `INT. LIGHTHOUSE - NIGHT` and click **＋ Create the first scene**.
- **＋ Add scene** in the navigator adds a scene after the selected one, in the same act.
- The navigator's scene actions move the selected scene up or down, move it to another act, or
  delete it. Deleting removes the scene, its blocks and its snapshots; beats and timeline events
  that pointed at it lose the link.
- **Continuous view** switches between one continuous page and page-by-page reading.

## Drafts

A project can hold several screenplays, called drafts. Importing a script creates a new draft named
"… (Imported)", and the **Draft** picker above the page switches between them. The Story twin and
the room always work from the draft you edited most recently.

## Live sync

Edits from another tab, from the room, or from an external agent over MCP appear in your open
workspace within a second. Your own tab ignores echoes of its own edits.

## Snapshots

Save a named snapshot of a scene from **Snapshots** in the context rail. You can diff two snapshots
and restore the heading, the blocks, or both. Restoring keeps block ids, so linked dialogue
translations survive.

## Instructions and translations

- **Project instruction** and **scene instruction** are notes the room reads before working on
  your project or on the selected scene.
- **Dialogue translation** keeps linked translations of dialogue in the project's other languages.
  Headings and action stay in the writing language.

## Import and export

| | Formats |
|---|---|
| Import | Fountain, Final Draft (`.fdx`), PDF |
| Export | PDF, Fountain, FDX, HTML |

Each import creates a new draft, so an import never overwrites your work. **Backup** writes a
checksummed archive of the whole project, and **Backups** lists them. Restoring always creates a new
project (see [Backups & recovery](backups.md)).

## Timeline

**Timeline** in the header opens the timeline board, where you can reorder scenes by dragging or
with the keyboard. A reorder is proposed, not applied: approve it to apply, and roll it back later if
you change your mind.
