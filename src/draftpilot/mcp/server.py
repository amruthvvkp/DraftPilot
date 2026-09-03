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
from draftpilot.crud import blocks as blocks_crud
from draftpilot.crud import dialogue_translations as translations_crud
from draftpilot.crud import scene_revisions as revisions_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.crud import acts as acts_crud
from draftpilot.crud import agent_proposals as proposals_crud
from draftpilot.models import AgentProposal, AgentProposalRead

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
async def read_project_artifacts(project_id: int, ctx: Context) -> dict[str, object]:
    """Read editable project artifacts through the authorized MCP boundary."""
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(session, client_id, project_id, "outline.read", "read", {})
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        artifacts = await artifacts_crud.list_for_project(session, project_id)
    result = {
        "project_id": project_id,
        "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
    }
    encoded = json.dumps(result)
    if len(encoded) > settings.mcp.max_output_chars:
        raise ValueError("Artifact response exceeds MCP output limit")
    return result


@mcp.tool
async def read_screenplay_scenes(
    project_id: int, screenplay_id: int, ctx: Context
) -> dict[str, object]:
    """Read ordered scenes and semantic blocks for one authorized screenplay."""
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(session, client_id, project_id, "screenplay.read", "read", {})
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        screenplay = await screenplays_crud.get(session, screenplay_id)
        if screenplay is None or screenplay.project_id != project_id:
            raise ValueError("Screenplay is not in the requested project")
        scenes = await scenes_crud.list_for_screenplay(session, screenplay_id)
        payload = []
        for scene in scenes:
            blocks = await blocks_crud.list_for_scene(session, scene.id or 0)
            payload.append(
                {
                    "scene": scene.model_dump(mode="json"),
                    "blocks": [block.model_dump(mode="json") for block in blocks],
                }
            )
    result = {"project_id": project_id, "screenplay_id": screenplay_id, "scenes": payload}
    if len(json.dumps(result)) > settings.mcp.max_output_chars:
        raise ValueError("Screenplay response exceeds MCP output limit")
    return result


@mcp.tool
async def read_dialogue_translations(
    project_id: int, scene_id: int, block_id: int, ctx: Context
) -> dict[str, object]:
    """Read linked dialogue translations without exposing unrelated project data."""
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session, client_id, project_id, "screenplay.read", "read", {"block_id": block_id}
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        scene = await scenes_crud.get(session, scene_id)
        block = await blocks_crud.get(session, block_id)
        act = await acts_crud.get(session, scene.act_id) if scene else None
        screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
        if (
            scene is None
            or block is None
            or block.scene_id != scene_id
            or screenplay is None
            or screenplay.project_id != project_id
        ):
            raise ValueError("Dialogue block is not in the requested project")
        translations = await translations_crud.list_for_block(session, block_id)
    result = {
        "project_id": project_id,
        "scene_id": scene_id,
        "block_id": block_id,
        "source_version": scene.version,
        "translations": [item.model_dump(mode="json") for item in translations],
    }
    if len(json.dumps(result)) > settings.mcp.max_output_chars:
        raise ValueError("Translation response exceeds MCP output limit")
    return result


@mcp.tool
async def propose_dialogue_translation(
    project_id: int,
    scene_id: int,
    block_id: int,
    language: str,
    text: str,
    ctx: Context,
) -> dict[str, object]:
    """Persist a reviewable translation proposal while preserving source dialogue."""
    if not language.strip() or len(language) > 50:
        raise ValueError("Translation language is invalid")
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "translation.propose",
                "propose",
                {"scene_id": scene_id, "block_id": block_id, "language": language},
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        scene = await scenes_crud.get(session, scene_id)
        block = await blocks_crud.get(session, block_id)
        act = await acts_crud.get(session, scene.act_id) if scene else None
        screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
        if (
            scene is None
            or block is None
            or block.scene_id != scene_id
            or block.element_type.value != "dialogue"
            or screenplay is None
            or screenplay.project_id != project_id
        ):
            raise ValueError("Dialogue block is not in the requested project")
        proposal = await proposals_crud.create(
            session,
            AgentProposal(
                project_id=project_id,
                target_kind="dialogue_translation",
                target_id=block_id,
                operation={"language": language, "text": text, "status": "draft"},
                diff={"source": block.text, "translation": text},
                before={"source_text": block.text, "source_version": scene.version},
                base_version=scene.version,
            ),
        )
    return AgentProposalRead.model_validate(proposal).model_dump(mode="json")


@mcp.tool
async def read_scene_revisions(project_id: int, scene_id: int, ctx: Context) -> dict[str, object]:
    """Read immutable scene snapshots for review and rollback planning."""
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session, client_id, project_id, "revisions.read", "read", {"scene_id": scene_id}
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        scene = await scenes_crud.get(session, scene_id)
        act = await acts_crud.get(session, scene.act_id) if scene else None
        screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
        if scene is None or screenplay is None or screenplay.project_id != project_id:
            raise ValueError("Scene is not in the requested project")
        revisions = await revisions_crud.list_for_scene(session, scene_id)
    result = {
        "project_id": project_id,
        "scene_id": scene_id,
        "revisions": [
            {**revision.model_dump(mode="json"), "snapshot": revision.snapshot}
            for revision in revisions
        ],
    }
    if len(json.dumps(result)) > settings.mcp.max_output_chars:
        raise ValueError("Revision response exceeds MCP output limit")
    return result


@mcp.tool
async def propose_screenplay_change(
    project_id: int,
    scene_id: int,
    operation: dict[str, object],
    diff: dict[str, object],
    ctx: Context,
) -> dict[str, object]:
    """Persist a typed screenplay proposal without applying creative changes."""
    client_id = ctx.client_id or "unknown"
    allowed = {"heading", "body"}
    if not operation or set(operation) - allowed:
        raise ValueError("Only heading and body operations are supported")
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "screenplay.propose",
                "propose",
                {"scene_id": scene_id, "operation_keys": sorted(operation)},
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        scene = await scenes_crud.get(session, scene_id)
        act = await acts_crud.get(session, scene.act_id) if scene else None
        screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
        if scene is None or screenplay is None or screenplay.project_id != project_id:
            raise ValueError("Scene is not in the requested project")
        before = {key: getattr(scene, key) for key in operation}
        proposal = await proposals_crud.create(
            session,
            AgentProposal(
                project_id=project_id,
                target_kind="scene",
                target_id=scene_id,
                operation=operation,
                diff=diff,
                before=before,
                base_version=scene.version,
            ),
        )
    return AgentProposalRead.model_validate(proposal).model_dump(mode="json")


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
