# Writers' room

DraftPilot's writers' room is a team of AI agents working for you, the one writer. They cover what a
human room does: bouncing the story, pitching ideas, drafting and rewriting scenes, fixing the
outline, and reading the script as an audience would. The room never changes your script or story on
its own. Anything that would change your work arrives as a **proposal** that you approve, reject or
later roll back.

## The team

| Role | What they do |
|---|---|
| Showrunner | Runs the room. Works out what you need, consults specialists, and brings back one answer |
| Story architect | Premise, spine, causality and theme |
| Story editor | Outlines, beat sheets and pacing across acts |
| Brainstormer | Divergent premises, twists, set pieces and alternatives |
| Character specialist | Wants, needs, flaws, arcs and relationships |
| Scene writer | Drafts and redrafts scenes in your voice |
| Script editor | Craft, clarity, rhythm and dialogue punch-up |
| Script doctor | Diagnoses what isn't working and prescribes targeted fixes |
| Researcher | Cited, project-relevant research |
| Continuity supervisor | Timeline, props, locations and established facts |
| Associate director | Visual language, camera and production feasibility |
| Audience evaluator | Reads the script as a particular viewer would |
| Coverage reader | Studio-style coverage with graded craft and a verdict |

Every agent works from two "twins":

- **The Story twin.** A live model of your project: its characters, their dialogue share and first
  appearance, and its locations. DraftPilot derives it from your working draft and refreshes it
  shortly after you edit. Whatever you write into a character or location yourself is never
  overwritten.
- **The Writer twin.** Who you are as a writer: your pen name, style notes, preferences and the
  things to avoid, plus memories you pin in **Settings**. It also learns from your decisions, such as
  how often you approve or reject each kind of proposal.

## Chat with the room

The chat on the right of every project page talks to the room ([Chat with the room](chat.md)).
**Showrunner** is the one to pick when you don't know who to ask: it plans, consults several
specialists in parallel, and answers once. Agents read your project through the same tools that
external agents use (see [MCP integration](mcp.md)), and they can only see the project you're in.

## Room workflows

Open **Writers' room ↗** from the workspace (or go to `/projects/<id>/room`). Pick a workflow, fill
in its form and start it. Runs are durable, so you can leave the page while one works; its trail of
steps updates live.

| Workflow | Who works on it | What you get |
|---|---|---|
| **Notes → outline** | Story editor ⇄ script doctor | A logline and beat outline, graded and revised until it reaches the target score or runs out of rounds. You get two proposals: the logline for your storyline and the beats for your outline |
| **Outline → scenes** | Scene writer, one per beat in parallel | New scenes drafted from your Outline's beats, proposed as one change that appends them to the draft |
| **Rewrite a scene** | Scene writer ⇄ script doctor | The scene rewritten to your brief, critiqued and revised, and proposed as a single reversible scene change |
| **Character arcs** | Character specialist, one per character in parallel | Want, need, flaw, turning points and a summary for the characters you name (or the Story twin's leads), proposed onto each character's profile, with a timeline event per turning point |
| **Brainstorm** | Brainstormers, one per lens in parallel, then the story architect | A ranked shortlist with reasons and a recommendation |
| **Audience panel** | One audience evaluator per persona, in parallel | Engagement per persona, the share who would recommend it, and the sticking points they have in common |
| **Coverage** | Coverage reader | Logline, synopsis, grades for premise, structure, character, dialogue and pacing, and a verdict |
| **Continuity pass** | Continuity supervisor | Continuity issues with the scenes they cite. Issues that cite scenes outside your draft are dropped |
| **Develop the story** | Story architect, character specialist, story editor ⇄ script doctor, scene writers, coverage reader | Your idea taken through storyline, cast, a timeline per lead, a critiqued outline and the first scenes, with coverage at the end. It pauses after every stage until you have decided its proposals, and builds only on what you approved ([Develop a story](guided-flow.md)) |

The two loops, **Notes → outline** and **Rewrite a scene**, run as evaluator-optimizer loops. The
drafter writes, the script doctor grades from 1 to 10, and the drafter revises until the score
reaches **Target score** or **Max rounds** runs out.

### Reviewing proposals

A finished run lists its proposals under **For your review**:

- **Approve** applies the change. A rewritten scene keeps its block ids and linked translations, and
  every changed block is marked as written by that proposal.
- **Reject** leaves your work untouched. The Writer twin records that you turned it down.
- **Roll back** undoes an approved change. Rolling back appended scenes is refused once you've edited
  one of them, so your own work is never discarded.

!!! tip "Speed on local models"
    Every step is a full agent run. On a local 27B reasoning model in LM Studio, one step takes from
    half a minute to several minutes, and most of that time is the model's reasoning. The graders
    (script doctor, audience evaluator, coverage reader and continuity supervisor) answer without
    reasoning by default. To speed runs up:

    - Set `LLM__THINKING=off` to turn reasoning off for every role, or `on` to force it everywhere.
      The default, `auto`, follows each role's spec.
    - Narrow the scope: pick specific scenes, set **Max rounds** to 1, or use fewer personas.

## External agents

Claude Code, Codex and any other MCP client can list and start the same workflows with
`list_room_workflows` and `start_room_workflow`. The same writer-approval rules apply to them. See
[MCP integration](mcp.md).
