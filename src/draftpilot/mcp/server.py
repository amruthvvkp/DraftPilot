"""FastMCP server exposing DraftPilot tools over the MCP protocol."""

import logfire
from fastmcp import FastMCP

from draftpilot.core import telemetry
from draftpilot.core.config import settings

telemetry.setup(mcp=True)

mcp = FastMCP(f"{settings.metadata.name.title()} MCP Server")

logfire.info("Telemetry setup complete")


@mcp.tool
def greet(name: str) -> str:
    """Return a greeting for the given name."""
    logfire.info("Greeting user", extra={"user_name": name})
    return f"Hello, {name}!"
