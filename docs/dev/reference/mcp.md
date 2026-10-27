# MCP server

DraftPilot's one tool surface, shared by external MCP clients and the in-app writers' room. Every
call is authorized per client and project and audited; writes that change the writer's work need a
writer-decided `approval_id`, or go through a `propose_*` tool that queues a reviewable proposal.
See [MCP](../../mcp.md) for the client-facing guide.

## Server

The FastMCP server: authentication, the typed capability boundary, prompts and resources. Importing
it configures telemetry (`telemetry.setup(mcp=True)`).

::: draftpilot.mcp.server

## Studio tools

The full screenplay-development surface: projects, storyline, characters with their timelines and
relationships, locations, the outline (acts and beats), scenes and blocks, revisions, imports,
proposals, the canon graph, artifacts and the Writer twin.

::: draftpilot.mcp.studio_tools

## The `draftpilot-mcp` package

The `draftpilot-mcp` wheel (`packages/draftpilot-mcp`) wraps the server above for MCP clients. It
depends on `draftpilot-studio` and adds one command, `draftpilot-mcp`:

| Command | What it does |
|---|---|
| `draftpilot-mcp` / `draftpilot-mcp serve` | Serve over stdio (the default; what MCP clients launch) |
| `draftpilot-mcp serve --http [--host 0.0.0.0] [--port 8000]` | Serve Streamable HTTP |
| `draftpilot-mcp trust CLIENT_ID [--name N] [--project ID] [--capability C ...]` | Register the client if new and grant capabilities; every capability when none (or `*`) is given, installation-wide when `--project` is omitted. Unknown capabilities are rejected |
| `draftpilot-mcp revoke CLIENT_ID [--project ID]` | Remove the client's grants on one project, or all of them |
| `draftpilot-mcp config {claude-code,claude-desktop,cursor,http} [--url U] [--token T]` | Print the snippet that connects that client (`--url` defaults to `http://localhost:9001/mcp`) |
| `draftpilot-mcp tools` | Print the server's tools, prompts and resources as JSON |
| `draftpilot-mcp --version` | Print the installed version |

`trust` and `revoke` talk to Postgres directly, so they read the same `POSTGRES__*` settings as the
server.

::: draftpilot_mcp.cli
