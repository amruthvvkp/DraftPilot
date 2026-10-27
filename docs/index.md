---
icon: lucide/rocket
---

# DraftPilot

DraftPilot is a local-first screenwriting studio for one writer and a room of AI agents. You write in
a proper screenplay editor. The **writers' room** reads your script and helps you think it through:

- it pitches and bounces story ideas;
- it outlines from your notes, drafts and rewrites scenes, and develops character arcs;
- it reads your script as an audience would.

Every change it wants to make arrives as a proposal that you approve. Everything runs on your
machine. By default the agents use a model in [LM Studio](https://lmstudio.ai).

## Start the studio

You need Docker and, for the agents, LM Studio with a chat model loaded (for example
`qwen/qwen3.8-27b`) and an embedding model (`text-embedding-nomic-embed-text-v1.5`).

```bash
git clone https://github.com/amruthvvkp/DraftPilot && cd DraftPilot
cp .env.example .env            # optional: every setting has a local default
docker compose up --build
```

No checkout needed: [Install](install.md) covers the published Compose stack, the Docker image, and
`pip install draftpilot-studio` / `uvx draftpilot-mcp`.

| Address | What it is |
|---|---|
| <http://localhost:9000> | The studio |
| <http://localhost:9001/mcp> | The MCP server for Claude, ChatGPT, Cursor and other agents |
| <http://localhost:8233> | The Temporal UI, which shows every room workflow and background job step by step |

If `API__TOKEN` is set, the studio asks for it once and then remembers you with a secure cookie.

## Your first ten minutes

1. **Create a project.** Click **New project** and give it a title. **Spark with AI** can suggest a
   logline and characters from a single line of premise.
2. **Follow the stepper.** Each project walks **Storyline → Characters → Outline → Script**
   ([Develop a story](guided-flow.md)). Fill the logline and premise, add your leads with what they
   want and need, sketch the acts and beats, then create the first scene from a beat.
3. **Or bring in a script.** In the Script, click **Import** and pick a `.fountain`, `.fdx` or `.pdf`
   (the Big Fish files in `tests/test_screenplays` are a good first test). The cast and locations
   fill in by themselves.
4. **Ask the room.** In the chat on the right, ask the showrunner something only your project can
   answer, or ask it to develop a stage. In **Edit with approval** mode it changes things directly,
   one approved step at a time ([Chat with the room](chat.md)).
5. **Let the room run the pipeline.** In **Writers' room**, start **Develop the story** with an idea,
   and approve each stage as it arrives.

## Where to go next

- [Develop a story](guided-flow.md) covers the stages, the context map and the pipeline.
- [Chat with the room](chat.md) covers roles, modes, in-chat approvals and threads.
- [Writing in the studio](editor.md) covers the editor, drafts, snapshots, translations and exports.
- [Writers' room](writers-room.md) covers the agent team, the workflows, and reviewing proposals.
- [Story tools](story-tools.md) covers the Story twin, Writer twin, knowledge graph and story studio.
- [Settings & appearance](settings.md) covers themes, your writer profile, memories and models.
- [Backups & recovery](backups.md) covers backups, restoring, and recently deleted projects.
- [MCP integration](mcp.md) connects Claude, ChatGPT or Cursor to develop screenplays through
  DraftPilot. The other advanced topics are [Provider setup](providers.md),
  [Evals & usefulness](evals.md) and [Deployment](deployment.md).
- If something isn't working, see [Troubleshooting](troubleshooting.md).
- To work on DraftPilot itself, start with the [Architecture](dev/architecture.md).
