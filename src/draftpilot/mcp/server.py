"""FastMCP server exposing DraftPilot's typed capability boundary."""

import json

import httpx
import logfire
from fastmcp import Context, FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier

from draftpilot.core import telemetry
from draftpilot.core.capabilities import capability_catalog
from draftpilot.core.db import session_scope
from draftpilot.crud.mcp_access import authorize_invocation
from draftpilot.core.screenplay.timeline import propose_reorder
from draftpilot.core.config import settings
from draftpilot.core.mcp_auth import valid_static_token
from draftpilot.crud import knowledge_graph as graph_crud

telemetry.setup(mcp=True)


class StaticTokenVerifier(TokenVerifier):
    """Verify the configured DraftPilot MCP bearer token."""

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return scoped access metadata for a valid configured token."""
        expected = settings.mcp.auth_token.get_secret_value()
        if not valid_static_token(token, expected):
            return None
        return AccessToken(token=token, client_id="mcp-client", scopes=["draftpilot"])


mcp = FastMCP(
    f"{settings.metadata.name.title()} MCP Server",
    auth=StaticTokenVerifier(required_scopes=["draftpilot"]),
)

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


@mcp.resource("draftpilot://schemas/context")
def context_schema_resource() -> str:
    """Publish the citation-bearing context response schema."""
    return json.dumps(
        {
            "query": "string",
            "results": [
                {
                    "text": "string",
                    "score": "number",
                    "citation": {
                        "project_id": "integer",
                        "source_id": "string",
                        "source_kind": "string",
                        "content_version": "integer",
                    },
                }
            ],
        }
    )


@mcp.resource("draftpilot://projects/{project_id}/knowledge-graph")
async def knowledge_graph_resource(project_id: int, ctx: Context) -> str:
    """Publish authorized canonical graph nodes and relationships for a project."""
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session, client_id, project_id, "knowledge_graph.read", "read", {}
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        nodes = await graph_crud.list_nodes(session, project_id)
        edges = await graph_crud.list_edges(session, project_id)
    return json.dumps(
        {
            "project_id": project_id,
            "nodes": [node.model_dump(mode="json") for node in nodes],
            "edges": [edge.model_dump(mode="json") for edge in edges],
        }
    )


@mcp.prompt
def workflow_turn(page: str, artifact: str = "", selection: str = "") -> str:
    """Build a page-aware workflow prompt without exposing credentials."""
    return (
        f"DraftPilot workflow page: {page}. Artifact: {artifact or 'none'}. "
        f"Selection: {selection or 'none'}. Propose typed changes for writer approval."
    )


@mcp.tool
async def retrieve_project_context(
    project_id: int,
    query: str,
    limit: int = 8,
    ctx: Context | None = None,
) -> dict[str, object]:
    """Retrieve citation-bearing project context through the RAG service."""
    if ctx is None:
        raise ValueError("MCP context is required")
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "context.read",
                "retrieve",
                {"query_length": len(query), "limit": limit},
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
    if not 1 <= limit <= 50 or not query.strip():
        raise ValueError("Query and limit are invalid")
    url = f"{settings.rag.service_url.rstrip('/')}/projects/{project_id}/search"
    headers = {"Authorization": f"Bearer {settings.rag.auth_token.get_secret_value()}"}
    async with httpx.AsyncClient(timeout=settings.mcp.request_timeout_seconds) as client:
        response = await client.post(url, json={"query": query, "limit": limit}, headers=headers)
        response.raise_for_status()
        if len(response.content) > settings.mcp.max_output_chars:
            raise ValueError("RAG response exceeds MCP output limit")
        result = response.json()
    if not isinstance(result, dict):
        raise ValueError("RAG response is invalid")
    return result


@mcp.tool
async def propose_timeline_reorder(
    project_id: int,
    current_scene_ids: list[int],
    proposed_scene_ids: list[int],
    durations: dict[int, int],
    ctx: Context,
) -> dict[str, object]:
    """Return a reversible, non-mutating timeline proposal."""
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "timeline.propose",
                "propose",
                {"scene_count": len(current_scene_ids)},
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
    proposal = propose_reorder(current_scene_ids, proposed_scene_ids, durations)
    return proposal.model_dump(mode="json")
