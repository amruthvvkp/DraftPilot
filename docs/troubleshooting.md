---
icon: lucide/life-buoy
---

# Troubleshooting

Most problems come from one of the services behind the studio being down: the model server, the
worker that runs the room, or the stack itself. Start by checking which services are running:

```bash
docker compose ps
```

Every service (`postgres`, `redis`, `temporal`, `ui`, `worker`, `mcp`, `rag`) should be up, and
`migrate` should have exited successfully. `docker compose logs <service>` shows what one of them
said.

## The chat says no model is available

The chat answers in red with **Retry** and keeps your message. What it says tells you where to look:

| The chat says | Cause | Fix |
|---|---|---|
| **No LLM provider is enabled** | `LLM__ENABLED=false`, or the profile picked under **Model** is disabled | set `LLM__ENABLED=true`, or pick **Default** or an enabled profile |
| **Model provider unavailable: …** | the model server can't be reached, or it has no chat model | see [LM Studio is unreachable](#lm-studio-is-unreachable-or-has-no-model) |
| **Temporal is unavailable: …** | the service that runs the room is down | see [The room never starts](#the-room-or-a-workflow-never-starts) |

**Spark with AI** in the new-project wizard does not fail this way: without a model, it fills the
brief from your premise with a simpler, built-in method.

## LM Studio is unreachable or has no model

**What you see:** the chat says **Model provider unavailable**, and **Settings → Default model
server** shows **Provider could not be reached** instead of a list of models.

1. Start LM Studio's local server (in the app, or `lms server start`).
2. Load a chat model (in the app, or `lms load <model>`). With `LLM__MODEL=auto`, the default,
   DraftPilot uses the first model LM Studio reports as loaded. If none is loaded it picks the first
   one LM Studio offers; if LM Studio has no chat model at all, you see "No chat model is available
   from lm_studio".
3. Check the address. `LLM__BASE_URL` is `http://host.docker.internal:1234/v1` in the Compose stack
   and should be `http://localhost:1234/v1` when DraftPilot runs outside Docker.
4. Reload **Settings**: the loaded models are marked **loaded**.

If you change `LLM__` settings in `.env`, apply them with `docker compose up -d`. Other providers are
in [Provider setup](providers.md).

## The room or a workflow never starts

**What you see:** a run started from the Writers' room or the chat stays **queued**, the chat shows
**The room is working…** and never answers, or the chat says **Temporal is unavailable**.

Chat turns, room workflows, context workflows and indexing all run in the **worker**, which takes its
work from **Temporal**. Both must be running.

1. Run `docker compose ps`. If `worker` isn't up, start it with `docker compose up -d worker` and
   read `docker compose logs worker` if it stops again.
2. If `temporal` isn't healthy, start it with `docker compose up -d temporal`.
3. Open the Temporal UI at <http://localhost:8233>. Each run is a workflow (named `run-<id>`) in the
   `default` namespace on the `draftpilot` task queue. A workflow that sits there without progress
   usually means no worker is polling that queue.

A run that was queued while the worker was down starts once the worker is back. Outside Docker, run
`temporal server start-dev` and `uv run draftpilot worker` (or `draftpilot worker`) next to the
studio.

## The stack won't start after pulling new code

**What you see:** `ui`, `worker` or `migrate` exits right away, or the studio fails on a new page.

The images still contain the old code (and the old migrations), so rebuild them:

```bash
docker compose up -d --build
```

`migrate` then brings the database up to date, and the other services start after it.

!!! note "Don't delete the volumes"
    Never run `docker compose down -v` to "start clean". It deletes the volumes, and with them your
    projects (`pgdata`), your backups (`backup_data`), the search index (`rag_data`) and Temporal's
    history. Rebuilding is enough.

## Search finds names but not meaning

**What you see:** nothing fails, but the room's retrieval only finds exact words.

Retrieval uses an embedding model for meaning and full-text search for exact names. If the
embedding model is missing, DraftPilot keeps working on full-text search alone.

1. Load `text-embedding-nomic-embed-text-v1.5` in LM Studio (`lms load
   text-embedding-nomic-embed-text-v1.5`), or set `RAG__EMBEDDING_MODEL` (and
   `RAG__EMBEDDING_BASE_URL`, `RAG__EMBEDDING_DIMENSIONS`) to the model you use.
2. Rebuild the project's index so earlier text gets embedded:
   `POST /api/v1/projects/{project_id}/rag/reindex`.
3. Check the result: `GET /api/v1/projects/{project_id}/rag/stats` reports `chunks`, `documents` and
   `embedded_chunks`.

If the `rag` service itself is down, retrieval answers **Retrieval service unavailable**; start it
with `docker compose up -d rag`.

## An MCP client can't connect

1. Check the server: `curl http://localhost:9001/health`. If it fails, start it with
   `docker compose up -d mcp`.
2. Over HTTP, connect to `http://localhost:9001/mcp` with `Authorization: Bearer <MCP__AUTH_TOKEN>`
   (`draftpilot-local-token` unless you changed it).
3. If it connects but every tool fails with **Capability is not granted for this client and
   project**, the client hasn't been trusted yet: `uvx draftpilot-mcp trust mcp-stdio` (for a stdio
   client), or grant capabilities with the admin token.
4. **Writer approval is required for this capability** is not an error: approve the request in the
   studio, then let the client retry.

[MCP integration](mcp.md) has the connection snippets for each client and the trust commands.
