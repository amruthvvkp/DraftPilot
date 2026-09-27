# Writing in the studio

The workspace has three columns:

- on the left, the **navigator**: your scenes with their estimated runtime, and a pacing gauge
  against the format's target length;
- in the middle, the **page**;
- on the right, the **context rail**: instructions, translations, snapshots, creative context and
  Copilot.

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
- To change a block's type, pick a new one and click **Review format**. The change is recorded as a
  proposal, so formatting fixes can be reviewed and undone like any other edit.
- Hover over a block, or focus it, to reveal its tools: move it up or down, delete it, and see who
  last wrote it. The authorship chip reads *agent* once an approved proposal wrote the block, and it
  disappears after you edit the block yourself.

Fountain markup such as `**bold**` is kept as you typed it and exported as-is.

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
