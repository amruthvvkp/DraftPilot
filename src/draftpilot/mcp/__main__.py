"""Run the DraftPilot MCP server over local stdio."""

from draftpilot.mcp.server import mcp


def main() -> None:
    """Start the MCP server using the protocol-safe stdio transport."""
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
