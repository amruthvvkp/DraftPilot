"""Verify the authenticated local MCP Streamable HTTP contract."""

import asyncio
import os

from draftpilot.core.mcp_client import DraftPilotMCPClient


async def main() -> None:
    """Discover tools and read one project-scoped resource."""
    client = DraftPilotMCPClient(
        os.getenv("DRAFTPILOT_MCP_ENDPOINT", "http://localhost:9001/mcp"),
        token=os.getenv("DRAFTPILOT_MCP_TOKEN", "draftpilot-local-token"),
    )
    project_id = int(os.getenv("DRAFTPILOT_MCP_PROJECT_ID", "4"))
    tools = await client.list_tools()
    resources = await client.list_resources()
    artifact_data = await client.read_resource(
        os.getenv("DRAFTPILOT_MCP_RESOURCE", f"draftpilot://projects/{project_id}/artifacts")
    )
    tool_data = await client.call_tool("read_project_artifacts", {"project_id": project_id})
    tool_count = len(tools["tools"]) if isinstance(tools, dict) and "tools" in tools else 0
    resource_count = (
        len(resources["resources"])
        if isinstance(resources, dict) and "resources" in resources
        else 0
    )
    print(
        f"tools={tool_count} resources={resource_count} "
        f"artifact_type={type(artifact_data).__name__} tool_type={type(tool_data).__name__}"
    )


if __name__ == "__main__":
    asyncio.run(main())
