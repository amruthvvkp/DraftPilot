from fastmcp import FastMCP

from draftpilot.core.config import settings

mcp = FastMCP(f"{settings.metadata.name.title()} MCP Server")


@mcp.tool
def greet(name: str) -> str:
    return f"Hello, {name}!"
