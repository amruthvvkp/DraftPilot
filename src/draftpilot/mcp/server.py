import logfire
from fastmcp import FastMCP

from draftpilot.core import telemetry
from draftpilot.core.config import settings

telemetry.setup(mcp=True)

mcp = FastMCP(f"{settings.metadata.name.title()} MCP Server")

logfire.info("Telemetry setup complete")


@mcp.tool
def greet(name: str) -> str:
    logfire.info(f"Greeting {name}")
    return f"Hello, {name}!"
