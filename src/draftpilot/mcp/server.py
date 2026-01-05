from fastmcp import FastMCP

from draftpilot.core.config import settings

mcp = FastMCP(f"{settings.metadata.name.title()} MCP Server")


@mcp.tool
def greet(name: str) -> str:
    """Greet someone by name.

    :param name: The name of the person to greet.
    :return: A greeting message.
    """
    return f"Hello, {name}!"
