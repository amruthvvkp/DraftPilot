---
icon: lucide/messages-square
---

# Chat with the room

The chat sits on the right of every project page. It knows where you are (the page, the scene you
are in, your selection) and talks to the writers' room through DraftPilot's own tools, so everything
it can do, you could also do by hand.

## Open and close the dock

On a wide screen (1440 pixels or more) the dock starts open; on a smaller one it starts collapsed.
**⟩** in the dock's header collapses it to a **✦ Chat** button, and that button opens it again.
DraftPilot remembers your choice in this browser.

Type in **Message the room** and press ++enter++ (++shift+enter++ for a new line), or press
**Send**. While the room works you see **The room is working…** and a **Stop** button. After an
answer, **Regenerate** asks for another version of it.

## Who you talk to

Pick a role. The **showrunner** (the default) plans the job, consults specialists — several at once
when the questions are independent — and brings back one answer. You can also talk to one specialist
directly: the story architect, story editor, character specialist, scene writer, script doctor,
continuity supervisor, coverage reader and the others.

The role is the **Who** list under the dock's header. Next to it, **May** sets what the room may do
(below), and **Model** picks the model.

## Which model answers

**Model** appears once you have added an enabled provider in **Settings → Add provider**
([Provider setup](providers.md)). **Default** uses the installation's model server (local LM Studio
unless you changed the `LLM__` settings); choose a profile to send this conversation's turns to that
provider instead. Your API keys stay on the server.

## What it may do

| Mode | The room can |
|---|---|
| **Ask only** | read your project and answer; it describes changes in prose |
| **Propose** (default) | also create proposals you review, and start room workflows |
| **Edit with approval** | also change the project directly — but each change waits for you in the chat |

In **Edit with approval**, when the room wants to write (add a character, rewrite a scene, rename an
act), its turn stops on an approval card that shows exactly what it will do. **Approve** runs that
exact change and the room carries on; **Deny** (optionally with a reason) tells it no, and nothing is
written. An approval covers that one call with those arguments, and nothing else.

## What it knows about where you are

Every message carries your place in the studio, so you can say "this scene" or "tighten this":

- **the page** you are on (Storyline, a character, the Outline, the Script…);
- on the **Script**, the scene you have selected (its heading and id);
- in the **Story studio**, the artifact you have open;
- on the **Knowledge graph**, the node type you are adding.

The empty dock says so: "It sees the page you are on", followed by your current selection.
The room also reads your project instruction, your writer profile and the story brief (the same brief
as the [context map](guided-flow.md#the-context-map)) before it answers.

## For your review

When any agent — this chat, a room workflow or an external MCP client — has proposals waiting, the
dock shows **For your review** with their number, above the conversation. Each proposal shows what
it changes:

- **Approve change** applies it;
- **Reject** discards it.

Your three most recently approved proposals stay listed with **Roll back**, which undoes the change.

## What it shows you

Answers are rendered as text, and the room's work as cards: its plan as a checklist, characters,
outlines, proposals you can approve or reject in place, the scenes it wrote (with a link to open them)
and the progress of the workflows it started. When it reads your project, you see which tools it
used.

| Card | Appears when the room | Lets you |
|---|---|---|
| **Plan** | makes a plan | follow its steps |
| **Character** / **New character** | reads or adds a character | open the character |
| **Outline** / **Proposed outline** | reads or proposes the outline | open the Outline |
| **Consulted a specialist** / **Consulted specialists** | asks one or more specialists | open each one's brief and answer |
| **New scene** / **Rewrote** | writes or rewrites a scene | open the scene |
| **Room run** | starts a workflow or an evaluation | follow its status and stages, then **Review in the writers' room** |
| A proposal | proposes a change | **Approve proposal** or **Reject proposal** in place |

The room can also move you around the studio: it can open a page or a scene for you, and the chat
notes **Opened a page** or **Opened a scene**.

## Conversations

Each conversation is a thread, kept by the server. Start a new one, switch between them, rename or
delete them; reopening a thread shows it as you left it.

- **New** in the dock's header (or **＋ New conversation**) starts a fresh thread.
- **Conversations** lists the project's threads, newest first. Click one to reopen it.
- **✎** renames a thread; **✕** deletes it after you confirm. Deleting removes the conversation and
  its history. Anything it changed in the project stays.

## When the room can't answer

If no model is available, the dock shows the reason in red with a **Retry** button, and your message
stays in the conversation:

| You see | What it means |
|---|---|
| **No LLM provider is enabled** | the default provider (or the profile you picked) is switched off |
| **Model provider unavailable: …** | the model server could not be reached, or it has no chat model |
| **Temporal is unavailable: …** | the background service that runs the room is down |

Fix the cause, then press **Retry**. [Troubleshooting](troubleshooting.md) walks through each one.
