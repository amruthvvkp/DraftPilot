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

Then open these addresses:

| Address | What it is |
|---|---|
| <http://localhost:9000> | The studio |
| <http://localhost:9001/mcp> | The MCP server for Claude Code, Codex and other agents |
| <http://localhost:8233> | The Temporal UI, which shows every room workflow and background job step by step |

If `API__TOKEN` is set, the studio asks for it once and then remembers you with a secure cookie.

## Your first ten minutes

1. **Create a project.** Click **New project** and give it a title. **Spark with AI** can suggest a
   logline and characters from a single line of premise.
2. **Bring in a script, or start from nothing.**
   - *Import:* in the workspace, click **Import** and pick a `.fountain`, `.fdx` or `.pdf`. The Big
     Fish files in `tests/test_screenplays` are a good first test.
   - *From notes:* open **Writers' room** and run **Notes → outline**, then **Outline → scenes**.
   - *From scratch:* add a scene, type a heading, and write action, character and dialogue blocks.
     ++tab++ moves between blocks, and smart typing picks the element for you.
3. **Look at the Story twin.** Open **Story twin** to see what the room now knows: your cast, ranked
   by how much each character speaks, and your locations.
4. **Ask the room.** In **Writers' room**, ask the showrunner something only your script can answer,
   such as "What does Will want from his father?". Its tools show up as it reads.
5. **Put the room to work.** Run **Rewrite a scene** on one scene and approve or reject the result.

## Where to go next

- [Writing in the studio](editor.md) covers the editor, drafts, snapshots, translations and exports.
- [Story tools](story-tools.md) covers the Story twin, knowledge graph, story studio and timeline.
- [Writers' room](writers-room.md) covers the agent team, the workflows, and reviewing proposals.
- [Settings & appearance](settings.md) covers themes, your writer profile, memories and models.
- [Manual test checklist](checklist.md) walks through every workflow by hand.
- For the advanced topics, see [MCP integration](mcp.md), [Evals & usefulness](evals.md) and
  [Deployment](deployment.md).
- To work on DraftPilot itself, start with the [Architecture](dev/architecture.md).
