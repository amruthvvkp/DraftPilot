"""Test the discoverable FastMCP prompt, resource, and tool surface."""

import pytest

from _async import run_async


def test_mcp_surface_exposes_context_and_graph_contracts() -> None:
    """Expose the typed retrieval tool, workflow prompt, and graph template."""
    pytest.importorskip("fastmcp")
    from draftpilot.mcp.server import mcp

    async def inspect_surface() -> tuple[list[str], list[str], list[str], list[str]]:
        """Read registered MCP prompts, resources, and tools."""
        prompts = [item.name for item in await mcp.list_prompts()]
        resources = [item.uri_template for item in await mcp.list_resource_templates()]
        static_resources = [str(item.uri) for item in await mcp.list_resources()]
        tools = [item.name for item in await mcp.list_tools()]
        return prompts, resources, static_resources, tools

    prompts, resources, static_resources, tools = run_async(inspect_surface())
    assert "workflow_turn" in prompts
    assert "draftpilot://projects/{project_id}/knowledge-graph" in resources
    assert "draftpilot://projects/{project_id}/artifacts" in resources
    assert "draftpilot://projects/{project_id}/context" in resources
    assert "draftpilot://context-workflows" in static_resources
    assert "retrieve_project_context" in tools
    assert "propose_timeline_reorder" in tools
    assert "review_timeline_proposal" in tools
    assert "review_screenplay_proposal" in tools
    assert "create_screenplay_export" in tools
    assert "read_project_artifacts" in tools
    assert "apply_story_operation" in tools
    assert "start_context_workflow" in tools
    assert "apply_context_workflow" in tools
    assert "read_project_evaluations" in tools
    assert "read_screenplay_scenes" in tools
    assert "propose_screenplay_change" in tools
    assert "read_dialogue_translations" in tools
    assert "propose_dialogue_translation" in tools
    assert "read_scene_revisions" in tools
    assert "render_screenplay_export" in tools
    assert "list_project_backups" in tools
    assert "create_project_backup" in tools
    assert "restore_project_backup" in tools
    assert "read_workflow_run" in tools
    assert "control_workflow_run" in tools


def test_mcp_surface_exposes_liveness_route() -> None:
    """Expose a public liveness route for container orchestration."""
    pytest.importorskip("fastmcp")
    from draftpilot.mcp.server import mcp

    routes = {route.path for route in mcp.http_app().routes}
    assert "/health" in routes
