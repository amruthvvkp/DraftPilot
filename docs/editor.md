# Writing in the studio

The workspace has three columns:

- on the left, the **navigator**: your scenes with their estimated runtime, and a pacing gauge
  against the format's target length;
- in the middle, the **page**;
- on the right, the **context rail** (instructions, translations, snapshots, creative context and
  **External agent approvals**) and the **chat** with the room ([Chat with the room](chat.md)).

Requests from an external agent over MCP that need your approval wait under **External agent
approvals**: **Approve request** or **Reject** each one (see [MCP integration](mcp.md)).

## Two editors

**Settings → Editor** chooses how you write the script. Both save to the same draft, and you can
switch at any time.

- **Classic** (the default for now): one box per element, one scene at a time. The rest of this
  page up to [Scenes](#scenes) describes it.
- **Document**: the whole draft as one continuous page, with the outline inline. See
  [The Document editor](#the-document-editor).

Document will become the default once every browser journey passes on both editors, and Classic
goes one release after that.

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

## The Document editor

The Document editor shows the draft as one page: the title page at the top, then each act, its
beats and its scenes. You can select across elements and scenes and move through the script with the
arrow keys, the way you would in Final Draft.

### Typing

| Key | In | Gives |
|---|---|---|
| ++enter++ | action | a new action |
| ++enter++ | character | dialogue |
| ++enter++ | dialogue | action (press it again on the empty line for a character) |
| ++enter++ | parenthetical | dialogue |
| ++enter++ | scene heading | the scene's first line |
| ++tab++ | action | character |
| ++tab++ | dialogue | parenthetical |
| ++tab++ | character | transition |
| ++shift+tab++ | any | the previous type in that cycle |
| ++shift+enter++ | any | a line break inside the element |

++cmd+1++ to ++cmd+9++ set the element type: section, action, character, parenthetical, dialogue,
transition, shot, lyric, note (++cmd+2++ to ++cmd+7++ match Final Draft). Browsers that keep
++cmd+1++–++cmd+9++ for switching tabs also accept ++cmd+alt+1++ to ++cmd+alt+9++.

Smart typing still applies when you press ++enter++: `EDWARD` becomes a character cue, `(beat)` a
parenthetical and `CUT TO:` a transition. Character cues are saved in upper case.

Pasting plain text adds one element per line, reading Fountain marks (`**bold**`, `*italic*`) and
cues as it goes.

### Formatting

Select text and a toolbar appears: undo and redo, the element type, **bold**, *italic*, underline,
strike, the amber mark and, on dialogue, **Pair with previous dialogue** (dual dialogue). ++cmd+b++,
++cmd+i++ and ++cmd+u++ work too. The **Current element type** picker above the page changes the
element under the cursor.

Formatting shows as formatting, not as markup. It is still stored as Fountain markup (`**bold**`,
`*italic*`, `_underline_`, `~~strike~~` and `[[color:#dda05d]]…[[/color]]`), so exports, search and
the agents see the same text as before. A line you didn't touch keeps its exact text.

### The outline in the page

Acts and the outline's beats appear as tinted headings above the scenes they link to. They are not
part of the script and don't print.

- Edit a beat's title or summary in place; it saves to the outline. If someone changed the beat in
  the meantime, the save is refused and the latest version loads.
- A beat with no scene yet shows **Create scene from beat**, which adds a scene at that point and
  links it to the beat.
- The **Outline** switch above the page hides acts and beats for a clean read. The arrow on an act
  or a beat collapses it.
- The **«** and **»** buttons collapse the navigator and the context rail, so the page can take
  the full width. Clicking a scene in the navigator moves the cursor to its heading.

Adding, deleting and moving scenes stays in the navigator: the page won't delete a scene by
selecting across it.

### Saving

Each scene you change is saved about a second after you stop typing, as one write for the whole
scene. The status above the page reads *Unsaved changes*, *Saving…* and *All changes saved*.

### Changes from elsewhere

When another tab, the room or an external agent changes a scene:

- if you haven't touched that scene, it updates in place and your cursor stays where it was;
- if you have unsaved edits there, or your save arrives after someone else's, a bar on the scene
  offers **Keep mine** (save your version over theirs) or **Load theirs** (drop your edits).

### Agent suggestions

A proposal from an agent appears under the lines it would change: the words it would remove are
struck through, the words it would add are underlined, and the agent and its summary sit on top.
Nothing changes until you click **Accept**; **Reject** dismisses it. An accepted change offers
**Roll back** on its line. A proposal is made against a saved version of the scene, so accept it
before editing that scene, or ask the agent again afterwards.

When you chat with the room, the dock sends the text you have selected and the ids of its blocks,
so "punch up these two lines" knows exactly which lines you mean.

### Not yet in the Document editor

- The title page card shows what an import brought in; editing it needs a title-page route.
- Dialogue translations are edited in the context rail, as in Classic.

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
