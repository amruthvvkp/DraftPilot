# Manual test checklist

Walk through this list on a running stack (`docker compose up`) with LM Studio serving a chat model
and `text-embedding-nomic-embed-text-v1.5`. The Big Fish files are in `tests/test_screenplays`. Tick
each item and note anything odd. Automated tests cover the same ground with mocks and scripted
models, so this checklist is the one place where the real model, real data and your judgement meet.

!!! tip "Timings"
    On a local 27B reasoning model, one room answer takes about 1–6 minutes, and a rewrite about
    10–20 minutes. Set `LLM__THINKING=off` for faster (if shallower) runs.

## 1. Access and appearance

- [ ] With `API__TOKEN` set, the studio asks for the token once; a wrong token is refused, and a
      reload keeps you signed in.
- [ ] **Settings → Appearance:** switch between Paper, Slate, Night and System. Every page stays
      readable, including the sidebar, cards, the editor, the room and the Story twin.
- [ ] Pick a custom accent. Buttons, badges and progress bars follow it. Open the studio in a second
      browser: the theme follows you.

## 2. Projects

- [ ] Create a project with the wizard; **Spark with AI** drafts a logline and characters from one line of premise.
- [ ] **⋯ → Duplicate** makes "… (copy)" with the same drafts.
- [ ] **⋯ → Delete…** stays disabled until you type the exact title. After deleting, the project
      appears under **Recently deleted**, and **Restore** brings it back complete.

## 3. Import and write

- [ ] Import `Big-Fish.fountain`: you get a new draft "… (Imported)" with 191 scenes. Also import the
      `.fdx` and the `.pdf`; they come out close, with the PDF the roughest.
- [ ] Switch drafts with the **Draft** picker.
- [ ] Edit an action line and blur it; it saves ("All changes local"). Open the same project in a
      second tab: your edit appears there within a second.
- [ ] ++tab++ moves from block to block, and character names autocomplete.
- [ ] Smart typing: type `CUT TO:` into an action line and leave it, and it becomes a transition. `EDWARD`
      becomes a character cue, and `(beat)` a parenthetical. Ordinary action is never retyped.
- [ ] Change a block's type and **Review format**; approve the proposal in Copilot.
- [ ] Page breaks show as dividers, text is never squeezed, and block tools appear on hover.
- [ ] Save a snapshot, change the scene, diff the two, and restore blocks only.
- [ ] Export PDF, Fountain, FDX and HTML; each opens and looks right.
- [ ] **Backup**, then **Backups → Restore copy** creates a new project.

## 4. Story twin

- [ ] **Story twin** lists Edward (about 307 lines), Will, Sandra, Jenny, Josephine… and locations
      such as Hospital Room and Bloom House.
- [ ] Write a note on Will. **Refresh from the draft** keeps your note and shows the *your note*
      badge.
- [ ] Rename a character in a scene. Within about ten seconds, the twin reflects it.

## 5. The room: chat

- [ ] **Writers' room → Talk to the room**, as the showrunner: "What does Will want from Edward?"
      Tool chips appear (Story twin, scenes, a specialist consult), and the answer cites scenes.
- [ ] As the script editor: "What is the heading of the second scene?" The answer is *INT. WILL'S
      BEDROOM - NIGHT (1973)*.
- [ ] Switch **May** to *Propose changes* and ask for a small fix; a proposal appears for review.

## 6. The room: workflows

For each workflow, start it, leave the page, come back, and check that the trail has advanced:

- [ ] **Rewrite a scene:** pick scene 2 with "Shorter, resentment in subtext". Check the script
      doctor's score, then **Approve**. The scene changes, with blocks marked *agent*. **Roll back**
      restores your text exactly.
- [ ] **Notes → outline:** paste a paragraph of notes. You get a logline and beats with a critique
      score. Approve both proposals, and the Brief and Outline artifacts update.
- [ ] **Beat board:** the approved outline's beats appear by act. Move one to Act 2, reorder, rewrite a
      summary and **Save outline**; the Outline artifact's version goes up.
- [ ] **Outline → scenes** (after the outline): new scenes are proposed. Approve, and they're
      appended to the draft; **Roll back** removes them unless you've edited one.
- [ ] **Character arcs** with no names: arcs for the leads land in the Characters artifact.
- [ ] **Brainstorm**, **Audience panel**, **Coverage** and **Continuity pass** each produce a readable
      report. The continuity pass cites only real scenes.
- [ ] **Cancel run** stops a workflow at its next step, and nothing is proposed.
- [ ] Automatic checks (✓/✗) appear on finished runs. 👍/👎 is saved.

## 7. Usefulness

- [ ] **How useful is the room?** shows accepted, kept, thumbs and time per workflow.
- [ ] Edit a block an approved rewrite wrote. **Kept** falls after a refresh.
- [ ] In the Temporal UI (<http://localhost:8233>), the run's `execute_workflow` shows each step, and
      a cancelled run ends as cancelled.

## 8. External agents (MCP)

- [ ] Connect Claude Code or Codex to `http://localhost:9001/mcp` (see [MCP integration](mcp.md))
      and list the tools.
- [ ] Read the project overview and a page of scenes.
- [ ] Call `start_room_workflow` with `coverage`; it appears in the studio's runs.
- [ ] Ask it to apply a story operation. The studio shows an approval request, and the call succeeds
      only with the approved id.

## 9. Offline evals

- [ ] `uv run python -m draftpilot.evals room_qa` completes and reports no regression against
      `evals/baselines/room_qa.json`.
