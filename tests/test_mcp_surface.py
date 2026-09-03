"""Test the discoverable FastMCP prompt, resource, and tool surface."""

import asyncio

import pytest


def test_mcp_surface_exposes_context_and_graph_contracts() -> None:
    """Expose the typed retrieval tool, workflow prompt, and graph template."""
    pytest.importorskip("fastmcp")
    from draftpilot.mcp.server import mcp

    async def inspect_surface() -> tuple[list[str], list[str], list[str]]:
        """Read registered MCP prompts, resources, and tools."""
        prompts = [item.name for item in await mcp.list_prompts()]
        resources = [item.uri_template for item in await mcp.list_resource_templates()]
        tools = [item.name for item in await mcp.list_tools()]
        return prompts, resources, tools

    prompts, resources, tools = asyncio.run(inspect_surface())
    assert "workflow_turn" in prompts
    assert "draftpilot://projects/{project_id}/knowledge-graph" in resources
    assert "retrieve_project_context" in tools
    assert "propose_timeline_reorder" in tools
    assert "read_project_artifacts" in tools
    assert "read_screenplay_scenes" in tools
    assert "propose_screenplay_change" in tools
    assert "read_dialogue_translations" in tools
    assert "propose_dialogue_translation" in tools
    assert "read_scene_revisions" in tools
    assert "render_screenplay_export" in tools
    assert "list_project_backups" in tools
    assert "read_workflow_run" in tools
