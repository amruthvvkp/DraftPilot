---
icon: lucide/package
---

# Install

DraftPilot ships four ways. They all run the same code and read the same settings
(`POSTGRES__`, `REDIS__`, `TEMPORAL__`, `LLM__`, `WEB__`, `MCP__`, `RAG__`, … — see `.env.example`).

| You want | Use |
|---|---|
| Everything on one machine, no build | [The Compose stack](#the-compose-stack) |
| The services in your own orchestration | [The Docker image](#the-docker-image) |
| DraftPilot in a Python environment | [The Python packages](#the-python-packages) |
| An MCP server for Claude, ChatGPT or Cursor | [`draftpilot-mcp`](#draftpilot-mcp) |

DraftPilot needs **Postgres 16 with pgvector**, **Redis** and a **Temporal** server. The Compose
stack brings all three. For the agents, run [LM Studio](https://lmstudio.ai) with a chat model and
`text-embedding-nomic-embed-text-v1.5` loaded, or configure another provider
([Provider setup](providers.md)).

## The Compose stack

Download `compose.yml`, `compose.release.yml` and `.env.example` from a
[GitHub release](https://github.com/amruthvvkp/DraftPilot/releases), then:

```bash
cp .env.example .env
docker compose -f compose.yml -f compose.release.yml up -d
```

The studio is on <http://localhost:9000>, the MCP server on <http://localhost:9001/mcp>, and the
Temporal UI on <http://localhost:8233>. Pin a release with `DRAFTPILOT_VERSION=0.1.0`. From a
checkout, `docker compose up --build` builds the same image locally instead.

## The Docker image

`ghcr.io/amruthvvkp/draftpilot` is one image for every service; the command picks the role:

```bash
docker run --rm ghcr.io/amruthvvkp/draftpilot migrate      # apply the schema
docker run -p 9000:8000 ghcr.io/amruthvvkp/draftpilot serve # API and studio
docker run ghcr.io/amruthvvkp/draftpilot worker             # Temporal worker (jobs, the room, chat)
docker run -p 9001:8000 ghcr.io/amruthvvkp/draftpilot mcp --http
docker run -p 9010:8000 ghcr.io/amruthvvkp/draftpilot rag
```

Pass the settings as environment variables. The image runs as a non-root user and keeps backups in
`/data/backups`; mount a volume there.

## The Python packages

```bash
pip install draftpilot-studio      # the studio, worker, MCP server and RAG service
draftpilot migrate                 # apply the schema to POSTGRES__*
draftpilot serve                   # API and studio on WEB__HOST:WEB__PORT (default :8000)
draftpilot worker                  # in another terminal
```

`draftpilot-studio` is the distribution name (`draftpilot` on PyPI is an unrelated project); the
module and the command are `draftpilot`. The wheel contains the built studio and the migrations.

## draftpilot-mcp

`draftpilot-mcp` packages the MCP server for MCP clients. It works on your DraftPilot database, so
what an agent does appears live in the studio, and every write still waits for your approval.

```bash
uvx draftpilot-mcp trust mcp-stdio        # let the local client work on every project
uvx draftpilot-mcp config claude-code     # prints: claude mcp add draftpilot -- uvx draftpilot-mcp
uvx draftpilot-mcp config claude-desktop  # prints the JSON for claude_desktop_config.json
uvx draftpilot-mcp tools                  # the 71 tools, 6 prompts and resources
```

See [MCP integration](mcp.md) for the tools, the guided prompts and how approvals work.

## From source

```bash
git clone https://github.com/amruthvvkp/DraftPilot && cd DraftPilot
uv sync --all-groups --all-packages
uv run draftpilot migrate
uv run draftpilot serve        # and `uv run draftpilot worker`
npm --prefix frontend run dev  # the studio with hot reload
```

`docker compose -f compose.yml -f compose.dev.yml up --build` runs the stack from your checkout with
live source mounts and debugpy ([Deployment](deployment.md)).
