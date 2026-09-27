"""FastMCP server exposing DraftPilot's typed capability boundary."""

import base64
import json
from datetime import UTC, datetime
from typing import Any

import logfire
from fastmcp import Context, FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from draftpilot.agents.workflow_runner import create_room_workflow_run
from draftpilot.agents.workflows import ROOM_WORKFLOWS
from draftpilot.api.agent import approve_agent_proposal, rollback_agent_proposal
from draftpilot.api.artifacts import _enqueue_index
from draftpilot.api.backups import (
    _enqueue_restored_artifacts,
    _project_payload,
    restore_backup_payload,
)
from draftpilot.api.timeline import (
    approve_timeline_proposal,
    rollback_timeline_proposal,
)
from draftpilot.core import events, rag_client, telemetry
from draftpilot.core.agent_identity import current_internal_agent
from draftpilot.core.backup import BackupError, read_backup, write_backup
from draftpilot.core.capabilities import capability_catalog
from draftpilot.core.config import settings
from draftpilot.core.context_operations import apply_context_suggestion
from draftpilot.core.context_workflows import (
    context_workflow_catalog,
    get_context_workflow,
    validate_context_source,
)
from draftpilot.core.db import session_scope
from draftpilot.core.exports import ExportError, write_export
from draftpilot.core.mcp_auth import client_id_for_token
from draftpilot.core.queue import enqueue_best_effort, get_arq_pool
from draftpilot.core.scene_proposals import (
    parse_scene_fountain,
    rewrite_operation,
    rewrite_snapshot,
)
from draftpilot.core.screenplay.adapters.fdx import render_fdx
from draftpilot.core.screenplay.adapters.fountain import render_fountain
from draftpilot.core.screenplay.html import render_html
from draftpilot.core.screenplay.hydrate import block_to_doc, load_screenplay_doc
from draftpilot.core.screenplay.pdf import render_pdf
from draftpilot.core.screenplay.schema import ActDoc, SceneDoc, ScreenplayDoc
from draftpilot.core.screenplay.timeline import propose_reorder
from draftpilot.core.story_operations import apply_story_operation as apply_operation
from draftpilot.core.story_operations import validate_story_operation
from draftpilot.core.twins import story_twin_brief, writer_twin_brief
from draftpilot.crud import acts as acts_crud
from draftpilot.crud import agent_proposals as proposals_crud
from draftpilot.crud import blocks as blocks_crud
from draftpilot.crud import dialogue_translations as translations_crud
from draftpilot.crud import evaluations as evaluations_crud
from draftpilot.crud import knowledge_graph as graph_crud
from draftpilot.crud import monty_executions as monty_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import scene_revisions as revisions_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.crud import timeline_proposals as timeline_proposals_crud
from draftpilot.crud import workflow_runs as runs_crud
from draftpilot.crud.mcp_access import authorize_invocation
from draftpilot.models import (
    AgentProposal,
    AgentProposalRead,
    BlockType,
    EvaluationResultRead,
    StoryArtifactRead,
    TimelineProposalRead,
    TimelineProposalRecord,
    WorkflowRunCreate,
    WorkflowRunRead,
)

telemetry.setup(mcp=True)


def _client_id(ctx: Context) -> str:
    """Resolve the authenticated client from MCP context or access-token metadata."""
    if (internal := current_internal_agent()) is not None:
        return internal.client_id
    context_client_id = ctx.client_id
    if context_client_id:
        return context_client_id
    access_token = get_access_token()
    return access_token.client_id if access_token is not None else settings.mcp.stdio_client_id


class StaticTokenVerifier(TokenVerifier):
    """Verify the configured DraftPilot MCP bearer token."""

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return scoped access metadata for a valid configured token."""
        client_id = client_id_for_token(
            token,
            settings.mcp.auth_token.get_secret_value(),
            settings.mcp.client_tokens,
        )
        if client_id is None:
            return None
        return AccessToken(token=token, client_id=client_id, scopes=["draftpilot"])


mcp = FastMCP(
    f"{settings.metadata.name.title()} MCP Server",
    auth=StaticTokenVerifier(required_scopes=["draftpilot"]),
)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    """Return MCP liveness without requiring project authentication."""
    return JSONResponse({"status": "ok", "service": "mcp"})

logfire.info("Telemetry setup complete")


@mcp.tool
def greet(name: str) -> str:
    """Return a greeting for the given name."""
    logfire.info("Greeting user", extra={"user_name": name})
    return f"Hello, {name}!"


@mcp.resource("draftpilot://capabilities")
def capabilities_resource() -> str:
    """Publish the discoverable, non-secret capability catalog."""
    return json.dumps(
        [capability.model_dump(mode="json") for capability in capability_catalog()]
    )


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
    client_id = _client_id(ctx)
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


@mcp.resource("draftpilot://projects/{project_id}/artifacts")
async def project_artifacts_resource(project_id: int, ctx: Context) -> str:
    """Publish authorized canonical story artifacts for a project."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(session, client_id, project_id, "outline.read", "read", {})
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        if await projects_crud.get(session, project_id) is None:
            raise ValueError("Project not found")
        artifacts = await artifacts_crud.list_for_project(session, project_id)
    result = {"project_id": project_id, "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts]}
    if len(json.dumps(result)) > settings.mcp.max_output_chars:
        raise ValueError("Artifact response exceeds MCP output limit")
    return json.dumps(result)


@mcp.resource("draftpilot://projects/{project_id}/context")
async def project_context_resource(project_id: int, ctx: Context) -> str:
    """Publish the authorized project context envelope for external clients."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(session, client_id, project_id, "context.read", "read", {})
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        project = await projects_crud.get(session, project_id)
        if project is None:
            raise ValueError("Project not found")
        artifacts = await artifacts_crud.list_for_project(session, project_id)
        nodes = await graph_crud.list_nodes(session, project_id)
        edges = await graph_crud.list_edges(session, project_id)
    result = {
        "project": project.model_dump(mode="json"),
        "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
        "knowledge_graph": {
            "nodes": [node.model_dump(mode="json") for node in nodes],
            "edges": [edge.model_dump(mode="json") for edge in edges],
        },
    }
    if len(json.dumps(result)) > settings.mcp.max_output_chars:
        raise ValueError("Project context response exceeds MCP output limit")
    return json.dumps(result)


@mcp.prompt
def workflow_turn(page: str, artifact: str = "", selection: str = "") -> str:
    """Build a page-aware workflow prompt without exposing credentials."""
    return (
        f"DraftPilot workflow page: {page}. Artifact: {artifact or 'none'}. "
        f"Selection: {selection or 'none'}. Propose typed changes for writer approval."
    )


@mcp.resource("draftpilot://context-workflows")
def context_workflows_resource() -> str:
    """Publish the reusable context-generation workflow contracts."""
    return json.dumps([workflow.model_dump(mode="json") for workflow in context_workflow_catalog()])


@mcp.tool
async def start_context_workflow(
    project_id: int,
    workflow: str,
    artifact_id: int,
    instruction: str,
    permission_mode: str = "suggest",
    ctx: Context | None = None,
) -> dict[str, object]:
    """Start one authorized, durable, review-only context workflow run."""
    if ctx is None:
        raise ValueError("MCP context is required")
    if permission_mode not in {"suggest", "scoped_edit", "project_edit"}:
        raise ValueError("Invalid context workflow permission mode")
    if not instruction.strip() or len(instruction) > 12_000:
        raise ValueError("Context workflow instruction is invalid")
    selected = get_context_workflow(workflow)
    if selected is None:
        raise ValueError("Unknown context workflow")
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "context.generate",
                "start",
                {"workflow": workflow, "artifact_id": artifact_id},
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        if await projects_crud.get(session, project_id) is None:
            raise ValueError("Project not found")
        artifact = await artifacts_crud.get(session, artifact_id)
        if artifact is None or artifact.project_id != project_id:
            raise ValueError("Context artifact not found")
        try:
            validate_context_source(selected, artifact.kind)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        run = await runs_crud.create(
            session,
            WorkflowRunCreate(
                project_id=project_id,
                kind="context_generation",
                input={
                    "workflow": selected.key,
                    "instruction": instruction,
                    "artifact_id": artifact_id,
                    "source_kind": artifact.kind,
                    "source_version": artifact.version,
                    "output_kind": selected.output_kind,
                    "evaluator": selected.evaluator,
                },
                agent_role=selected.agent_role,
                permission_mode=permission_mode,
            ),
        )
        await (await get_arq_pool()).enqueue_job("execute_workflow", run.id)
    return WorkflowRunRead.model_validate(run).model_dump(mode="json")


@mcp.tool
async def apply_context_workflow(
    project_id: int,
    run_id: int,
    expected_source_version: int,
    approval_id: int | None = None,
    ctx: Context | None = None,
) -> dict[str, object]:
    """Apply one approved context suggestion as a canonical graph node."""
    if ctx is None:
        raise ValueError("MCP context is required")
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "context.apply",
                "apply",
                {"run_id": run_id},
                approval_id=approval_id,
                arguments={"run_id": run_id, "expected_source_version": expected_source_version},
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        node = await apply_context_suggestion(session, project_id, run_id, expected_source_version)
    return {"project_id": project_id, "node": node.model_dump(mode="json"), "run_id": run_id}


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
    client_id = _client_id(ctx)
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
    return await rag_client.search(project_id, query, limit, timeout=settings.mcp.request_timeout_seconds)


@mcp.tool
async def read_project_artifacts(project_id: int, ctx: Context) -> dict[str, object]:
    """Read editable project artifacts through the authorized MCP boundary."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session, client_id, project_id, "outline.read", "read", {}
            )
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
async def apply_story_operation(
    project_id: int,
    artifact_id: int,
    operation: str,
    payload: dict[str, object],
    approval_id: int | None = None,
    ctx: Context | None = None,
) -> dict[str, object]:
    """Apply one approved typed story operation through the canonical artifact service."""
    if ctx is None:
        raise ValueError("MCP context is required")
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "story.operation",
                "apply",
                {"artifact_id": artifact_id, "operation": operation},
                approval_id=approval_id,
                arguments={"artifact_id": artifact_id, "operation": operation, "payload": payload},
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        artifact = await artifacts_crud.get(session, artifact_id)
        if artifact is None or artifact.project_id != project_id:
            raise ValueError("Artifact is not in the requested project")
        try:
            parsed = validate_story_operation(artifact.kind, operation, payload)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        apply_operation(artifact, parsed)
        artifact.updated_at = datetime.now(UTC)
        session.add(artifact)
        await artifacts_crud.mark_dependents_stale(session, project_id, [artifact_id])
        await session.commit()
        await session.refresh(artifact)
    await _enqueue_index(project_id, artifact)
    await events.publish(project_id, "artifact.changed", {"artifact_id": artifact.id, "version": artifact.version})
    return StoryArtifactRead.model_validate(artifact).model_dump(mode="json")


@mcp.tool
async def read_project_evaluations(project_id: int, ctx: Context) -> dict[str, object]:
    """Read persisted evaluation results through the authorized project boundary."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(session, client_id, project_id, "evaluations.read", "read", {})
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        if await projects_crud.get(session, project_id) is None:
            raise ValueError("Project not found")
        evaluations = await evaluations_crud.list_for_project(session, project_id)
    result = {
        "project_id": project_id,
        "evaluations": [
            EvaluationResultRead.model_validate(item).model_dump(mode="json")
            for item in evaluations
        ],
    }
    if len(json.dumps(result)) > settings.mcp.max_output_chars:
        raise ValueError("Evaluation response exceeds MCP output limit")
    return result


@mcp.tool
async def read_screenplay_scenes(
    project_id: int,
    screenplay_id: int,
    ctx: Context,
    scene_ids: list[int] | None = None,
    offset: int = 0,
    limit: int = 10,
    format: str = "fountain",
) -> dict[str, object]:
    """Read scenes: pick ``scene_ids`` or page with ``offset``/``limit``.

    ``format="fountain"`` (default) returns each scene as compact Fountain text; ``format="blocks"``
    returns the typed semantic blocks with ids, which block-level proposals need.
    """
    client_id = _client_id(ctx)
    limit = max(1, min(limit, 50))
    if format not in {"fountain", "blocks"}:
        raise ValueError("format must be 'fountain' or 'blocks'")
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session, client_id, project_id, "screenplay.read", "read", {}
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        screenplay = await screenplays_crud.get(session, screenplay_id)
        if screenplay is None or screenplay.project_id != project_id:
            raise ValueError("Screenplay is not in the requested project")
        all_scenes = await scenes_crud.list_for_screenplay(session, screenplay_id)
        if scene_ids:
            wanted = set(scene_ids)
            scenes = [scene for scene in all_scenes if scene.id in wanted][:limit]
        else:
            scenes = all_scenes[max(offset, 0) : max(offset, 0) + limit]
        blocks = await blocks_crud.list_for_scenes(session, [scene.id for scene in scenes if scene.id is not None])
    by_scene: dict[int, list[Any]] = {}
    for block in blocks:
        by_scene.setdefault(block.scene_id, []).append(block)
    if format == "fountain":
        rendered: list[dict[str, object]] = [
            {
                "scene_id": scene.id,
                "number": all_scenes.index(scene) + 1,
                "version": scene.version,
                "fountain": render_fountain(
                    ScreenplayDoc(
                        acts=[
                            ActDoc(
                                scenes=[
                                    SceneDoc(
                                        heading=scene.heading,
                                        blocks=[block_to_doc(block) for block in by_scene.get(scene.id or 0, [])],
                                    )
                                ]
                            )
                        ]
                    )
                ).strip(),
            }
            for scene in scenes
        ]
    else:
        rendered = [
            {"scene": scene.model_dump(mode="json"), "blocks": [block.model_dump(mode="json") for block in by_scene.get(scene.id or 0, [])]}
            for scene in scenes
        ]
    result = {
        "project_id": project_id,
        "screenplay_id": screenplay_id,
        "total_scenes": len(all_scenes),
        "offset": 0 if scene_ids else max(offset, 0),
        "format": format,
        "scenes": rendered,
    }
    if len(json.dumps(result)) > settings.mcp.max_output_chars:
        raise ValueError("Screenplay response exceeds MCP output limit; request fewer scenes")
    return result


@mcp.tool(annotations={"read_only_hint": True})
async def read_story_twin(project_id: int, ctx: Context) -> dict[str, object]:
    """Return the Story twin (characters, locations, canon, with scene links) and the Writer twin brief."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(session, client_id, project_id, "knowledge_graph.read", "read", {})
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        nodes = await graph_crud.list_nodes(session, project_id)
        story = await story_twin_brief(session, project_id)
        writer = await writer_twin_brief(session, project_id)

    def summary(node: Any) -> dict[str, object]:
        """Keep the fields an agent needs to reason and cite."""
        meta = node.node_metadata
        return {
            "node_id": node.id,
            "label": node.label,
            "description": node.description,
            "dialogue_lines": meta.get("dialogue_lines"),
            "scene_ids": (meta.get("scene_ids") or [])[:60],
            "first_scene_id": meta.get("first_scene_id"),
            "writer_owned": meta.get("source") != "twin_keeper" or bool(meta.get("writer_edited")),
        }

    characters = sorted((n for n in nodes if n.kind == "character"), key=lambda n: -int(n.node_metadata.get("dialogue_lines", 0)))
    locations = sorted((n for n in nodes if n.kind == "location"), key=lambda n: -len(n.node_metadata.get("scene_ids", [])))
    result: dict[str, object] = {
        "project_id": project_id,
        "characters": [summary(node) for node in characters[:60]],
        "locations": [summary(node) for node in locations[:60]],
        "canon": [summary(node) for node in nodes if node.kind not in {"character", "location"}][:60],
        "story_brief": story,
        "writer_brief": writer,
    }
    if len(json.dumps(result, default=str)) > settings.mcp.max_output_chars:
        raise ValueError("Story twin exceeds MCP output limit")
    return result


@mcp.tool(annotations={"read_only_hint": True})
async def read_project_overview(project_id: int, ctx: Context) -> dict[str, object]:
    """Return a compact project map: brief, drafts, a scene index (no block text), and artifacts."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(session, client_id, project_id, "screenplay.read", "read", {})
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        project = await projects_crud.get(session, project_id)
        if project is None:
            raise ValueError("Project not found")
        drafts: list[dict[str, Any]] = []
        for screenplay in await screenplays_crud.list_for_project(session, project_id):
            scenes = await scenes_crud.list_for_screenplay(session, screenplay.id or 0)
            drafts.append(
                {
                    "screenplay_id": screenplay.id,
                    "title": screenplay.title,
                    "format": screenplay.format,
                    "title_page": screenplay.title_page,
                    "scene_count": len(scenes),
                    "scene_index": [
                        {"scene_id": scene.id, "position": index + 1, "heading": scene.heading}
                        for index, scene in enumerate(scenes)
                    ],
                }
            )
        artifacts = await artifacts_crud.list_for_project(session, project_id)
    result: dict[str, object] = {
        "project": {
            "id": project.id,
            "title": project.title,
            "logline": project.logline,
            "genres": project.genres,
            "languages": project.languages,
            "project_instruction": project.project_instruction,
        },
        "drafts": drafts,
        "artifacts": [
            {"artifact_id": item.id, "kind": item.kind, "title": item.title, "version": item.version, "stale": item.stale}
            for item in artifacts
        ],
    }
    if len(json.dumps(result, default=str)) > settings.mcp.max_output_chars:
        for draft in drafts:
            draft["scene_index"] = draft["scene_index"][:400]
    return result


@mcp.tool
async def read_dialogue_translations(
    project_id: int, scene_id: int, block_id: int, ctx: Context
) -> dict[str, object]:
    """Read linked dialogue translations without exposing unrelated project data."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "screenplay.read",
                "read",
                {"block_id": block_id},
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        scene = await scenes_crud.get(session, scene_id)
        block = await blocks_crud.get(session, block_id)
        act = await acts_crud.get(session, scene.act_id) if scene else None
        screenplay = (
            await screenplays_crud.get(session, act.screenplay_id) if act else None
        )
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
    client_id = _client_id(ctx)
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
        screenplay = (
            await screenplays_crud.get(session, act.screenplay_id) if act else None
        )
        if (
            scene is None
            or block is None
            or block.scene_id != scene_id
            or block.element_type.value != "dialogue"
            or screenplay is None
            or screenplay.project_id != project_id
        ):
            raise ValueError("Dialogue block is not in the requested project")
        project = await projects_crud.get(session, project_id)
        allowed_languages = {
            item.strip().casefold()
            for item in project.languages
        } if project is not None else set()
        normalized_language = language.strip().casefold()
        if project is None or normalized_language not in allowed_languages:
            raise ValueError("Translation language is not enabled for this project")
        if normalized_language == project.primary_language.strip().casefold():
            raise ValueError("Primary screenplay language cannot be a translation target")
        proposal = await proposals_crud.create(
            session,
            AgentProposal(
                project_id=project_id,
                target_kind="dialogue_translation",
                target_id=block_id,
                operation={"language": language, "text": text, "status": "draft"},
                diff={"source": block.text, "translation": text},
                before={
                    "source_text": block.text,
                    "source_version": scene.version,
                    "scene_id": scene_id,
                    "exists": False,
                    "language": language,
                    "text": "",
                    "status": "draft",
                },
                base_version=scene.version,
            ),
        )
    return AgentProposalRead.model_validate(proposal).model_dump(mode="json")


@mcp.tool
async def read_scene_revisions(
    project_id: int, scene_id: int, ctx: Context
) -> dict[str, object]:
    """Read immutable scene snapshots for review and rollback planning."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "revisions.read",
                "read",
                {"scene_id": scene_id},
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        scene = await scenes_crud.get(session, scene_id)
        act = await acts_crud.get(session, scene.act_id) if scene else None
        screenplay = (
            await screenplays_crud.get(session, act.screenplay_id) if act else None
        )
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
async def render_screenplay_export(
    project_id: int, screenplay_id: int, file_format: str, ctx: Context
) -> dict[str, object]:
    """Render a bounded, project-authorized Fountain, FDX, HTML, or PDF export."""
    if file_format not in {"fountain", "fdx", "html", "pdf"}:
        raise ValueError("Only Fountain, FDX, HTML, and PDF exports are available through MCP")
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "exports.read",
                "read",
                {"screenplay_id": screenplay_id},
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        project = await projects_crud.get(session, project_id)
        screenplay = await screenplays_crud.get(session, screenplay_id)
        if project is None or screenplay is None or screenplay.project_id != project_id:
            raise ValueError("Screenplay is not in the requested project")
        document = await load_screenplay_doc(session, screenplay_id)
    if file_format == "pdf":
        content_base64 = base64.b64encode(render_pdf(document)).decode("ascii")
        if len(content_base64) > settings.mcp.max_output_chars:
            raise ValueError("Export response exceeds MCP output limit")
        return {
            "project_id": project_id,
            "screenplay_id": screenplay_id,
            "format": file_format,
            "content_base64": content_base64,
        }
    content = render_fountain(document) if file_format == "fountain" else render_fdx(document) if file_format == "fdx" else render_html(document)
    if len(content) > settings.mcp.max_output_chars:
        raise ValueError("Export response exceeds MCP output limit")
    return {
        "project_id": project_id,
        "screenplay_id": screenplay_id,
        "format": file_format,
        "content": content,
    }


@mcp.tool
async def create_screenplay_export(
    project_id: int,
    screenplay_id: int,
    file_format: str,
    approval_id: int | None = None,
    ctx: Context | None = None,
) -> dict[str, object]:
    """Persist an approved, bounded screenplay export artifact without changing its source."""
    if ctx is None:
        raise ValueError("MCP context is required")
    if file_format not in {"fountain", "fdx", "html", "pdf"}:
        raise ValueError("Only Fountain, FDX, HTML, and PDF exports are available through MCP")
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "exports.create",
                "create",
                {"screenplay_id": screenplay_id, "format": file_format},
                approval_id=approval_id,
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        project = await projects_crud.get(session, project_id)
        screenplay = await screenplays_crud.get(session, screenplay_id)
        if project is None or screenplay is None or screenplay.project_id != project_id:
            raise ValueError("Screenplay is not in the requested project")
        document = await load_screenplay_doc(session, screenplay_id)
    if file_format == "pdf":
        content = render_pdf(document)
    elif file_format == "fountain":
        content = render_fountain(document).encode()
    elif file_format == "html":
        content = render_html(document).encode()
    else:
        content = render_fdx(document).encode()
    try:
        artifact = write_export(
            settings.backup.root,
            project_id,
            screenplay_id,
            screenplay.title,
            file_format,
            content,
            settings.mcp.max_output_chars * 4,
        )
    except ExportError as exc:
        raise ValueError(str(exc)) from exc
    return {"project_id": project_id, "screenplay_id": screenplay_id, **artifact.__dict__}


@mcp.tool
async def list_project_backups(project_id: int, ctx: Context) -> dict[str, object]:
    """List validated backup manifests for one authorized project."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session, client_id, project_id, "backups.read", "read", {}
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        if await projects_crud.get(session, project_id) is None:
            raise ValueError("Project not found")
    results: list[dict[str, object]] = []
    if settings.backup.root.exists():
        for path in sorted(settings.backup.root.glob("*.json.gz")):
            try:
                envelope = read_backup(settings.backup.root, path.name)
            except BackupError:
                continue
            if envelope.manifest.project_id == project_id:
                results.append(
                    {
                        "filename": path.name,
                        "manifest": envelope.manifest.model_dump(mode="json"),
                    }
                )
    result = {"project_id": project_id, "backups": results}
    if len(json.dumps(result)) > settings.mcp.max_output_chars:
        raise ValueError("Backup response exceeds MCP output limit")
    return result


@mcp.tool
async def create_project_backup(
    project_id: int, approval_id: int | None = None, ctx: Context | None = None
) -> dict[str, object]:
    """Create an approved, project-scoped backup through the canonical backup service."""
    if ctx is None:
        raise ValueError("MCP context is required")
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "backups.create",
                "create",
                {},
                approval_id=approval_id,
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        project = await projects_crud.get(session, project_id)
        if project is None:
            raise ValueError("Project not found")
        payload = await _project_payload(session, project_id)
        filename, manifest = write_backup(
            settings.backup.root,
            project_id,
            payload,
            settings.metadata.version,
            project.title,
        )
    result = {
        "project_id": project_id,
        "filename": filename,
        "manifest": manifest.model_dump(mode="json"),
    }
    if len(json.dumps(result)) > settings.mcp.max_output_chars:
        raise ValueError("Backup response exceeds MCP output limit")
    return result


@mcp.tool
async def restore_project_backup(
    project_id: int,
    filename: str,
    approval_id: int | None = None,
    ctx: Context | None = None,
) -> dict[str, int]:
    """Restore an approved backup into a new project through the canonical restore service."""
    if ctx is None:
        raise ValueError("MCP context is required")
    client_id = _client_id(ctx)
    try:
        envelope = read_backup(settings.backup.root, filename)
    except BackupError as exc:
        raise ValueError("Invalid backup") from exc
    if envelope.manifest.project_id != project_id:
        raise ValueError("Backup is not in the requested project")
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "backups.restore",
                "restore",
                {"filename": filename},
                approval_id=approval_id,
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        restored = await restore_backup_payload(session, envelope.payload)
        if restored.id is None:
            raise ValueError("Restored project has no identifier")
        await _enqueue_restored_artifacts(session, restored.id)
    if restored.id is None:
        raise ValueError("Restored project has no identifier")
    return {"source_project_id": project_id, "project_id": restored.id}


@mcp.tool
async def read_workflow_run(
    project_id: int, run_id: int, ctx: Context
) -> dict[str, object]:
    """Read one durable workflow run within its project scope."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session, client_id, project_id, "runs.read", "read", {"run_id": run_id}
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        run = await runs_crud.get(session, run_id)
        if run is None or run.project_id != project_id:
            raise ValueError("Run is not in the requested project")
    return WorkflowRunRead.model_validate(run).model_dump(mode="json")


@mcp.tool
async def read_monty_executions(project_id: int, ctx: Context) -> dict[str, object]:
    """Read bounded, redacted Monty audit records for one authorized project."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session, client_id, project_id, "monty.audit.read", "read", {}
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        records = await monty_crud.list_for_project(session, project_id)
    result = {
        "project_id": project_id,
        "executions": [record.model_dump(mode="json") for record in records],
    }
    if len(json.dumps(result)) > settings.mcp.max_output_chars:
        raise ValueError("Monty audit response exceeds MCP output limit")
    return result


@mcp.tool
async def control_workflow_run(
    project_id: int,
    run_id: int,
    action: str,
    approval_id: int | None = None,
    ctx: Context | None = None,
) -> dict[str, object]:
    """Resume or cancel a durable run only after explicit writer approval."""
    if action not in {"resume", "cancel"}:
        raise ValueError("Run action must be resume or cancel")
    if ctx is None:
        raise ValueError("MCP context is required")
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "runs.control",
                action,
                {"run_id": run_id, "action": action},
                approval_id=approval_id,
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        run = await runs_crud.get(session, run_id)
        if run is None or run.project_id != project_id:
            raise ValueError("Run is not in the requested project")
        if action == "cancel":
            if run.status in {"succeeded", "failed", "cancelled"}:
                raise ValueError("Run is already terminal")
            await runs_crud.update_status(session, run, "cancelled")
        else:
            if run.status == "succeeded":
                raise ValueError("Run already succeeded")
            run.status = "queued"
            run.attempt_count = 0
            run.error = None
            session.add(run)
            await session.commit()
            await session.refresh(run)
            await (await get_arq_pool()).enqueue_job("execute_workflow", run.id)
    return WorkflowRunRead.model_validate(run).model_dump(mode="json")


@mcp.tool
async def list_room_workflows() -> list[dict[str, object]]:
    """List the writers' room workflows (notes→outline, rewrite, arcs, panel, coverage, ...) and their parameters."""
    return [
        {
            "key": workflow.key,
            "label": workflow.label,
            "description": workflow.description,
            "proposes": workflow.proposes,
            "params_schema": workflow.params.model_json_schema(),
        }
        for workflow in ROOM_WORKFLOWS.values()
    ]


@mcp.tool
async def start_room_workflow(
    project_id: int, workflow: str, params: dict[str, object], ctx: Context
) -> dict[str, object]:
    """Start a durable writers' room workflow; follow it with read_workflow_run. Results arrive as proposals or a report."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(session, client_id, project_id, "room.workflow", "start", {"workflow": workflow})
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        if await projects_crud.get(session, project_id) is None:
            raise ValueError("Project not found")
        try:
            run = await create_room_workflow_run(session, project_id, workflow, dict(params))
        except KeyError as exc:
            raise ValueError(f"Unknown room workflow; choose one of {', '.join(ROOM_WORKFLOWS)}") from exc
        except ValidationError as exc:
            raise ValueError(f"Invalid workflow parameters: {exc.errors(include_url=False)}") from exc
    await enqueue_best_effort("execute_workflow", run.id, description="room workflow enqueue")
    return WorkflowRunRead.model_validate(run).model_dump(mode="json")


@mcp.tool
async def propose_screenplay_change(
    project_id: int,
    scene_id: int,
    operation: dict[str, object],
    diff: dict[str, object],
    ctx: Context,
    block_id: int | None = None,
) -> dict[str, object]:
    """Persist a typed scene or semantic-block proposal without applying changes.

    To rewrite a whole scene, pass ``operation={"fountain": "<the scene in Fountain>"}`` without a block_id.
    """
    target_kind = "block" if block_id is not None else "scene"
    rewrite = block_id is None and set(operation) == {"fountain"}
    if rewrite:
        if not isinstance(operation["fountain"], str):
            raise ValueError("fountain must be the scene text")
        operation = rewrite_operation(parse_scene_fountain(operation["fountain"]))
    if block_id is not None:
        allowed = {"element_type", "text", "is_dual", "dual_group"}
    else:
        allowed = {"heading", "blocks"} if rewrite else {"heading", "body"}
    if not operation or set(operation) - allowed:
        raise ValueError("Unsupported typed screenplay operation")
    if block_id is not None:
        if "element_type" in operation and operation["element_type"] not in {item.value for item in BlockType}:
            raise ValueError("Invalid screenplay block type")
        if "text" in operation and not isinstance(operation["text"], str):
            raise ValueError("Invalid screenplay block text")
        if "is_dual" in operation and not isinstance(operation["is_dual"], bool):
            raise ValueError("Invalid dual-dialogue marker")
        if "dual_group" in operation and operation["dual_group"] is not None and not isinstance(operation["dual_group"], int):
            raise ValueError("Invalid dual-dialogue group")
    client_id = _client_id(ctx)
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
        screenplay = (
            await screenplays_crud.get(session, act.screenplay_id) if act else None
        )
        if scene is None or screenplay is None or screenplay.project_id != project_id:
            raise ValueError("Scene is not in the requested project")
        target_id = scene_id
        if block_id is not None:
            block = await blocks_crud.get(session, block_id)
            if block is None or block.scene_id != scene_id:
                raise ValueError("Block is not in the requested scene")
            target_id = block_id
            before = {
                "scene_id": scene_id,
                **{
                    key: (
                        getattr(block, key).value
                        if key == "element_type"
                        else getattr(block, key)
                    )
                    for key in operation
                },
            }
        elif rewrite:
            before = await rewrite_snapshot(session, scene)
        else:
            before = {key: getattr(scene, key) for key in operation}
        proposal = await proposals_crud.create(
            session,
            AgentProposal(
                project_id=project_id,
                target_kind=target_kind,
                target_id=target_id,
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
    screenplay_id: int,
    current_scene_ids: list[int],
    proposed_scene_ids: list[int],
    durations: dict[int, int],
    ctx: Context,
) -> dict[str, object]:
    """Persist a reversible timeline proposal after validating current order."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "timeline.propose",
                "propose",
                {"screenplay_id": screenplay_id, "scene_count": len(current_scene_ids)},
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        screenplay = await screenplays_crud.get(session, screenplay_id)
        if screenplay is None or screenplay.project_id != project_id:
            raise ValueError("Screenplay is not in the requested project")
        scenes = await scenes_crud.list_for_screenplay(session, screenplay_id)
        server_scene_ids = [scene.id for scene in scenes if scene.id is not None]
        if server_scene_ids != current_scene_ids:
            raise ValueError("Screenplay order has changed")
        try:
            calculated = propose_reorder(current_scene_ids, proposed_scene_ids, durations)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        record = await timeline_proposals_crud.create(
            session,
            TimelineProposalRecord(
                project_id=project_id,
                screenplay_id=screenplay_id,
                original_scene_ids=current_scene_ids,
                proposed_scene_ids=calculated.scene_ids,
                timings=[timing.model_dump() for timing in calculated.timings],
                total_runtime_seconds=calculated.total_runtime_seconds,
            ),
        )
    return TimelineProposalRead.model_validate(record).model_dump(mode="json")


@mcp.tool
async def review_screenplay_proposal(
    project_id: int,
    proposal_id: int,
    action: str,
    approval_id: int | None = None,
    ctx: Context | None = None,
) -> dict[str, object]:
    """Approve or roll back a typed screenplay proposal through REST logic."""
    if action not in {"approve", "rollback"} or ctx is None:
        raise ValueError("Action and MCP context are required")
    capability = "screenplay.approve" if action == "approve" else "screenplay.rollback"
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(session, client_id, project_id, capability, action, {"proposal_id": proposal_id}, approval_id=approval_id)
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        result = await (
            approve_agent_proposal(project_id, proposal_id, session)
            if action == "approve"
            else rollback_agent_proposal(project_id, proposal_id, session)
        )
    return result.model_dump(mode="json")


@mcp.tool
async def review_timeline_proposal(
    project_id: int,
    screenplay_id: int,
    proposal_id: int,
    action: str,
    approval_id: int | None = None,
    ctx: Context | None = None,
) -> dict[str, object]:
    """Approve or roll back a timeline proposal through REST logic."""
    if action not in {"approve", "rollback"} or ctx is None:
        raise ValueError("Action and MCP context are required")
    capability = "timeline.approve" if action == "approve" else "timeline.rollback"
    client_id = _client_id(ctx)
    async with session_scope() as session:
        try:
            await authorize_invocation(session, client_id, project_id, capability, action, {"screenplay_id": screenplay_id, "proposal_id": proposal_id}, approval_id=approval_id)
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        result = await (
            approve_timeline_proposal(project_id, screenplay_id, proposal_id, session)
            if action == "approve"
            else rollback_timeline_proposal(project_id, screenplay_id, proposal_id, session)
        )
    return result.model_dump(mode="json")
