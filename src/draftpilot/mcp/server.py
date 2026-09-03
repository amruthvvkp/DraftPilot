"""FastMCP server exposing DraftPilot's typed capability boundary."""

import json

import httpx
import logfire
from fastmcp import Context, FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier

from draftpilot.core import telemetry
from draftpilot.core.capabilities import capability_catalog
from draftpilot.core.db import session_scope
from draftpilot.core.queue import get_arq_pool
from draftpilot.crud.mcp_access import authorize_invocation
from draftpilot.core.screenplay.timeline import propose_reorder
from draftpilot.core.config import settings
from draftpilot.core.mcp_auth import client_id_for_token
from draftpilot.core.backup import BackupError, read_backup, write_backup
from draftpilot.api.backups import _project_payload, restore_backup_payload
from draftpilot.core.screenplay.hydrate import load_screenplay_doc
from draftpilot.core.screenplay.adapters.fdx import render_fdx
from draftpilot.core.screenplay.adapters.fountain import render_fountain
from draftpilot.crud import knowledge_graph as graph_crud
from draftpilot.crud import blocks as blocks_crud
from draftpilot.crud import dialogue_translations as translations_crud
from draftpilot.crud import scene_revisions as revisions_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.crud import acts as acts_crud
from draftpilot.crud import agent_proposals as proposals_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import workflow_runs as runs_crud
from draftpilot.models import AgentProposal, AgentProposalRead
from draftpilot.models import WorkflowRunRead

telemetry.setup(mcp=True)


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
                before={"source_text": block.text, "source_version": scene.version, "scene_id": scene_id,
                        "exists": False, "language": language, "text": "", "status": "draft"},
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
async def render_screenplay_export(
    project_id: int, screenplay_id: int, file_format: str, ctx: Context
) -> dict[str, object]:
    """Render a bounded, project-authorized Fountain or FDX export."""
    if file_format not in {"fountain", "fdx"}:
        raise ValueError("Only Fountain and FDX exports are available through MCP")
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session, client_id, project_id, "exports.read", "read", {"screenplay_id": screenplay_id}
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        project = await projects_crud.get(session, project_id)
        screenplay = await screenplays_crud.get(session, screenplay_id)
        if project is None or screenplay is None or screenplay.project_id != project_id:
            raise ValueError("Screenplay is not in the requested project")
        document = await load_screenplay_doc(session, screenplay_id)
    content = render_fountain(document) if file_format == "fountain" else render_fdx(document)
    if len(content) > settings.mcp.max_output_chars:
        raise ValueError("Export response exceeds MCP output limit")
    return {"project_id": project_id, "screenplay_id": screenplay_id, "format": file_format, "content": content}


@mcp.tool
async def list_project_backups(project_id: int, ctx: Context) -> dict[str, object]:
    """List validated backup manifests for one authorized project."""
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(session, client_id, project_id, "backups.read", "read", {})
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
                results.append({"filename": path.name, "manifest": envelope.manifest.model_dump(mode="json")})
    result = {"project_id": project_id, "backups": results}
    if len(json.dumps(result)) > settings.mcp.max_output_chars:
        raise ValueError("Backup response exceeds MCP output limit")
    return result


@mcp.tool
async def create_project_backup(
    project_id: int, approved: bool = False, ctx: Context | None = None
) -> dict[str, object]:
    """Create an approved, project-scoped backup through the canonical backup service."""
    if ctx is None:
        raise ValueError("MCP context is required")
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "backups.create",
                "create",
                {},
                approved=approved,
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
    result = {"project_id": project_id, "filename": filename, "manifest": manifest.model_dump(mode="json")}
    if len(json.dumps(result)) > settings.mcp.max_output_chars:
        raise ValueError("Backup response exceeds MCP output limit")
    return result


@mcp.tool
async def restore_project_backup(
    project_id: int,
    filename: str,
    approved: bool = False,
    ctx: Context | None = None,
) -> dict[str, int]:
    """Restore an approved backup into a new project through the canonical restore service."""
    if ctx is None:
        raise ValueError("MCP context is required")
    client_id = ctx.client_id or "unknown"
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
                approved=approved,
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        restored = await restore_backup_payload(session, envelope.payload)
    if restored.id is None:
        raise ValueError("Restored project has no identifier")
    return {"source_project_id": project_id, "project_id": restored.id}


@mcp.tool
async def read_workflow_run(project_id: int, run_id: int, ctx: Context) -> dict[str, object]:
    """Read one durable workflow run within its project scope."""
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(session, client_id, project_id, "runs.read", "read", {"run_id": run_id})
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc
        run = await runs_crud.get(session, run_id)
        if run is None or run.project_id != project_id:
            raise ValueError("Run is not in the requested project")
    return WorkflowRunRead.model_validate(run).model_dump(mode="json")


@mcp.tool
async def control_workflow_run(
    project_id: int,
    run_id: int,
    action: str,
    approved: bool = False,
    ctx: Context | None = None,
) -> dict[str, object]:
    """Resume or cancel a durable run only after explicit writer approval."""
    if action not in {"resume", "cancel"}:
        raise ValueError("Run action must be resume or cancel")
    if ctx is None:
        raise ValueError("MCP context is required")
    client_id = ctx.client_id or "unknown"
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                client_id,
                project_id,
                "runs.control",
                action,
                {"run_id": run_id, "action": action},
                approved=approved,
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
            run.error = None
            session.add(run)
            await session.commit()
            await session.refresh(run)
            await (await get_arq_pool()).enqueue_job("execute_workflow", run.id)
    return WorkflowRunRead.model_validate(run).model_dump(mode="json")


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
