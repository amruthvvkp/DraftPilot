# draftpilot-mcp

The [DraftPilot](https://github.com/amruthvvkp/DraftPilot) MCP server as its own package: develop
screenplays end to end (storyline, characters with motives and timelines, outline, scenes,
revisions, reviews) from Claude Desktop, Claude Code, ChatGPT or any MCP client. It works on the
same DraftPilot database as the studio (`pip install draftpilot-studio`), so everything an agent does shows up live for the writer,
and every write waits for the writer's approval.

```bash
uvx draftpilot-mcp                       # serve over stdio (what MCP clients launch)
uvx draftpilot-mcp serve --http          # or Streamable HTTP on :8000
uvx draftpilot-mcp trust mcp-stdio       # let a client work on every project
uvx draftpilot-mcp config claude-code    # print the snippet to connect a client
uvx draftpilot-mcp tools                 # list the tools, prompts and resources
```

Point it at your DraftPilot installation with the same environment as the studio, for example
`POSTGRES__HOST`, `POSTGRES__PORT`, `POSTGRES__PASSWORD`, `REDIS__HOST`, `TEMPORAL__HOST`. See the
[MCP guide](https://github.com/amruthvvkp/DraftPilot/blob/main/docs/mcp.md) for the tools and the
approval flow.
