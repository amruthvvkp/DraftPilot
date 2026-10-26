"""DraftPilot's MCP server, packaged for MCP clients (Claude, ChatGPT, Cursor, ...)."""

__all__ = ["server"]


def server() -> object:
    """Return DraftPilot's FastMCP server (imported lazily: loading it configures telemetry)."""
    from draftpilot.mcp.server import mcp

    return mcp
