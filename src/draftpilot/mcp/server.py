"""FastMCP server exposing DraftPilot's typed capability boundary."""

import json

import logfire
from fastmcp import FastMCP

from draftpilot.core import telemetry
from draftpilot.core.capabilities import capability_catalog
from draftpilot.core.screenplay.timeline import propose_reorder
from draftpilot.core.config import settings

telemetry.setup(mcp=True)

mcp = FastMCP(f"{settings.metadata.name.title()} MCP Server")

logfire.info("Telemetry setup complete")


@mcp.tool
def greet(name: str) -> str:
    """Return a greeting for the given name."""
    logfire.info("Greeting user", extra={"user_name": name})
    return f"Hello, {name}!"


@mcp.resource("draftpilot://capabilities")
def capabilities_resource() -> str:
    """Publish the discoverable, non-secret capability catalog."""
    return json.dumps([capability.model_dump(mode="json") for capability in capability_catalog()])


@mcp.prompt
def workflow_turn(page: str, artifact: str = "", selection: str = "") -> str:
    """Build a page-aware workflow prompt without exposing credentials."""
    return (
        f"DraftPilot workflow page: {page}. Artifact: {artifact or 'none'}. "
        f"Selection: {selection or 'none'}. Propose typed changes for writer approval."
    )


@mcp.tool
def propose_timeline_reorder(
    current_scene_ids: list[int], proposed_scene_ids: list[int], durations: dict[int, int]
) -> dict[str, object]:
    """Return a reversible, non-mutating timeline proposal."""
    proposal = propose_reorder(current_scene_ids, proposed_scene_ids, durations)
    return proposal.model_dump(mode="json")
