"""Studio services not covered by ``core/story``: projects, artifacts, canon graph, revisions, imports, writer twin.

Shared by the REST API and the MCP server so both enforce the same scope, versioning and
side effects.
"""

import difflib
import json
from datetime import UTC, datetime
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import events, indexing, temporal
from draftpilot.core.errors import Conflict, Invalid, NotFound, check_version
from draftpilot.core.project_backup import (
    enqueue_restored_documents,
    project_payload,
    restore_payload,
)
from draftpilot.core.project_lifecycle import delete_project as backup_and_purge
from draftpilot.core.scene_sync import scene_changed
from draftpilot.core.screenplay.adapters.fdx import parse_fdx
from draftpilot.core.screenplay.adapters.fountain import parse_fountain
from draftpilot.core.screenplay.hydrate import save_screenplay_doc
from draftpilot.core.story.storyline import project_text
from draftpilot.core.story.structure import (
    require_project,
    scene_in_project,
    screenplay_in_project,
    versioned_scene,
)
from draftpilot.core.twins import get_writer_profile
from draftpilot.crud import knowledge_graph as graph_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import scene_revisions as revisions_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.models import (
    KnowledgeEdge,
    KnowledgeNode,
    KnowledgeNodeCreate,
    Project,
    ProjectCreate,
    ProjectReferenceBase,
    Scene,
    SceneRevision,
    Screenplay,
    ScreenplayCreate,
    StoryArtifact,
    WriterMemory,
    WriterProfile,
)

MAX_IMPORT_BYTES = 10 * 1024 * 1024

# --- projects ----------------------------------------------------------------------------------


async def create_project(
    session: AsyncSession, data: ProjectCreate, references: list[ProjectReferenceBase] | None = None
) -> Project:
    """Create a project with its first draft and Act One, and index its brief."""
    project = await projects_crud.create_with_references(session, data, references or [])
    assert project.id is not None
    await indexing.index_document(project.id, f"project:{project.id}", "project", project_text(project), project.version)
    return project


async def duplicate_project(session: AsyncSession, project_id: int, title: str | None = None) -> Project:
    """Copy a project's brief, story, artifacts and every draft into a new project."""
    payload = await project_payload(session, project_id)
    payload["project"]["title"] = (title or f"{payload['project']['title']} (copy)")[:200]
    project = await restore_payload(session, payload)
    await enqueue_restored_documents(session, project.id or 0)
    await temporal.start_best_effort("reindex_project", project.id, description="RAG reindex enqueue")
    await temporal.start_best_effort("refresh_story_twin", project.id, description="Story twin refresh enqueue")
    return project


async def delete_project(session: AsyncSession, project_id: int) -> dict[str, Any]:
    """Back the project up, then delete it with everything in it."""
    payload = await project_payload(session, project_id)
    try:
        result = await backup_and_purge(session, project_id, payload)
    except LookupError as exc:
        raise NotFound("Project not found") from exc
    await temporal.start_best_effort("purge_rag_project", project_id, description="RAG project purge enqueue")
    await events.publish(project_id, "project.deleted", {"backup": result["backup"]})
    return result


# --- artifacts ---------------------------------------------------------------------------------


async def _index_artifact(project_id: int, artifact: StoryArtifact) -> None:
    """Refresh an artifact's RAG document and announce the change."""
    await indexing.index_document(project_id, f"artifact:{artifact.id}", artifact.kind, artifact.content, artifact.version)
    await events.publish(project_id, "artifact.changed", {"artifact_id": artifact.id, "version": artifact.version})


async def validate_dependencies(session: AsyncSession, project_id: int, artifact_id: int | None, dependencies: list[int]) -> None:
    """Reject missing, cross-project, self-referential, or cyclic artifact dependencies."""
    if len(dependencies) != len(set(dependencies)):
        raise Invalid("Artifact dependencies must be unique")
    by_id = {artifact.id: artifact for artifact in await artifacts_crud.list_for_project(session, project_id) if artifact.id is not None}
    if set(dependencies) - set(by_id):
        raise Invalid("Artifact dependencies must belong to this project")
    if artifact_id is not None and artifact_id in dependencies:
        raise Invalid("An artifact cannot depend on itself")
    if artifact_id is None:
        return
    graph = {identifier: list(artifact.depends_on) for identifier, artifact in by_id.items()}
    graph[artifact_id] = dependencies
    pending, visited = list(dependencies), set[int]()
    while pending:
        dependency_id = pending.pop()
        if dependency_id == artifact_id:
            raise Invalid("Artifact dependencies cannot contain cycles")
        if dependency_id not in visited:
            visited.add(dependency_id)
            pending.extend(graph.get(dependency_id, []))


async def create_artifact(
    session: AsyncSession, project_id: int, kind: str, title: str, content: str = "", depends_on: list[int] | None = None,
    metadata: dict[str, Any] | None = None,
) -> StoryArtifact:
    """Create an editable story artifact (brief, outline, bible, notes, ...)."""
    await require_project(session, project_id)
    if not title.strip():
        raise Invalid("Artifact title cannot be empty")
    await validate_dependencies(session, project_id, None, depends_on or [])
    artifact = StoryArtifact(
        project_id=project_id, kind=kind[:40], title=title[:200], content=content, depends_on=depends_on or [], artifact_metadata=metadata or {}
    )
    session.add(artifact)
    await session.commit()
    await session.refresh(artifact)
    await _index_artifact(project_id, artifact)
    return artifact


async def update_artifact(
    session: AsyncSession, project_id: int, artifact_id: int, changes: dict[str, Any], expected_version: int | None
) -> StoryArtifact:
    """Edit an artifact under optimistic concurrency and mark its dependents stale."""
    artifact = await artifacts_crud.get(session, artifact_id)
    if artifact is None or artifact.project_id != project_id:
        raise NotFound("Artifact not found")
    check_version(expected_version, artifact.version, "Artifact")
    changes = dict(changes)
    if set(changes) - {"title", "content", "depends_on", "metadata", "artifact_metadata", "stale"}:
        raise Invalid("Unsupported artifact field")
    if "depends_on" in changes:
        await validate_dependencies(session, project_id, artifact_id, changes["depends_on"])
    if "metadata" in changes:
        changes["artifact_metadata"] = changes.pop("metadata")
    for key, value in changes.items():
        setattr(artifact, key, value)
    artifact.version += 1
    artifact.stale = bool(changes.get("stale", False))
    artifact.updated_at = datetime.now(UTC)
    session.add(artifact)
    await artifacts_crud.mark_dependents_stale(session, project_id, [artifact_id])
    await session.commit()
    await session.refresh(artifact)
    await _index_artifact(project_id, artifact)
    return artifact


async def delete_artifact(session: AsyncSession, project_id: int, artifact_id: int, expected_version: int | None) -> None:
    """Delete an artifact and drop it from other artifacts' dependencies."""
    artifact = await artifacts_crud.get(session, artifact_id)
    if artifact is None or artifact.project_id != project_id:
        raise NotFound("Artifact not found")
    check_version(expected_version, artifact.version, "Artifact")
    for other in await artifacts_crud.list_for_project(session, project_id):
        if artifact_id in other.depends_on:
            other.depends_on = [item for item in other.depends_on if item != artifact_id]
            session.add(other)
    await session.delete(artifact)
    await session.commit()
    await indexing.delete_document(project_id, f"artifact:{artifact_id}")
    await events.publish(project_id, "artifact.changed", {"artifact_id": artifact_id, "deleted": True})


# --- canon graph -------------------------------------------------------------------------------


async def _index_node(project_id: int, node: KnowledgeNode) -> None:
    """Refresh a canon node's RAG document and announce it."""
    await indexing.index_document(
        project_id, f"knowledge_node:{node.id}", f"knowledge_node:{node.kind}", f"{node.label}\n{node.description or ''}", node.version
    )
    await events.publish(project_id, "graph.changed", {"node_id": node.id, "version": node.version})


async def create_node(
    session: AsyncSession, project_id: int, kind: str, label: str, description: str | None = None, metadata: dict[str, Any] | None = None
) -> KnowledgeNode:
    """Add a canon node (theme, motif, rule, prop, era, ...) to the project graph."""
    await require_project(session, project_id)
    node = await graph_crud.create_node(
        session,
        KnowledgeNodeCreate(project_id=project_id, kind=kind[:60], label=label[:300], description=description, node_metadata=metadata or {}),
    )
    await _index_node(project_id, node)
    return node


async def update_node(session: AsyncSession, project_id: int, node_id: int, changes: dict[str, Any], expected_version: int | None) -> KnowledgeNode:
    """Edit a canon node; a writer edit makes it writer-owned."""
    node = await graph_crud.get_node(session, node_id)
    if node is None or node.project_id != project_id:
        raise NotFound("Graph node not found")
    check_version(expected_version, node.version, "Graph node")
    if set(changes) - {"kind", "label", "description", "node_metadata"}:
        raise Invalid("Unsupported graph node field")
    for key, value in changes.items():
        setattr(node, key, value)
    node.node_metadata = {**node.node_metadata, "writer_edited": True}
    node.version += 1
    node.updated_at = datetime.now(UTC)
    session.add(node)
    await session.commit()
    await session.refresh(node)
    await _index_node(project_id, node)
    return node


async def delete_node(session: AsyncSession, project_id: int, node_id: int, expected_version: int | None) -> None:
    """Delete a canon node together with its relationships."""
    node = await graph_crud.get_node(session, node_id)
    if node is None or node.project_id != project_id:
        raise NotFound("Graph node not found")
    check_version(expected_version, node.version, "Graph node")
    edges = (
        await session.exec(
            select(KnowledgeEdge).where((col(KnowledgeEdge.source_node_id) == node_id) | (col(KnowledgeEdge.target_node_id) == node_id))
        )
    ).all()
    for edge in edges:
        await session.delete(edge)
    await session.flush()
    await session.delete(node)
    await session.commit()
    await indexing.delete_document(project_id, f"knowledge_node:{node_id}")
    await events.publish(project_id, "graph.changed", {"node_id": node_id, "deleted": True})


async def create_edge(
    session: AsyncSession, project_id: int, source_node_id: int, target_node_id: int, relation: str, metadata: dict[str, Any] | None = None
) -> KnowledgeEdge:
    """Relate two canon nodes of the same project."""
    source = await graph_crud.get_node(session, source_node_id)
    target = await graph_crud.get_node(session, target_node_id)
    if source is None or target is None or source.project_id != project_id or target.project_id != project_id:
        raise NotFound("Graph node not found")
    edge = await graph_crud.create_edge(
        session,
        KnowledgeEdge(project_id=project_id, source_node_id=source_node_id, target_node_id=target_node_id, relation=relation[:100], edge_metadata=metadata or {}),
    )
    await indexing.index_document(project_id, f"knowledge_edge:{edge.id}", "knowledge_edge", f"{source.label} {relation} {target.label}", 1)
    await events.publish(project_id, "graph.changed", {"edge_id": edge.id})
    return edge


async def delete_edge(session: AsyncSession, project_id: int, edge_id: int) -> None:
    """Remove one canon relationship."""
    edge = await graph_crud.get_edge(session, edge_id)
    if edge is None or edge.project_id != project_id:
        raise NotFound("Graph edge not found")
    await graph_crud.delete_edge(session, edge)
    await indexing.delete_document(project_id, f"knowledge_edge:{edge_id}")
    await events.publish(project_id, "graph.changed", {"edge_id": edge_id, "deleted": True})


# --- revisions ---------------------------------------------------------------------------------


async def snapshot_scene(session: AsyncSession, project_id: int, scene_id: int, message: str | None = None) -> SceneRevision:
    """Capture an immutable, named snapshot of a scene."""
    scene = await scene_in_project(session, project_id, scene_id)
    return await revisions_crud.snapshot(session, scene, message)


async def _revision(session: AsyncSession, scene_id: int, revision_id: int) -> SceneRevision:
    """Return a revision of the scene or raise ``NotFound``."""
    revision = await revisions_crud.get(session, revision_id)
    if revision is None or revision.scene_id != scene_id:
        raise NotFound("Revision not found")
    return revision


async def restore_revision(
    session: AsyncSession, project_id: int, scene_id: int, revision_id: int, expected_version: int | None, sections: set[str] | None = None
) -> Scene:
    """Restore a scene's heading and/or blocks from a revision (id-stable where blocks still exist)."""
    scene = await versioned_scene(session, project_id, scene_id, expected_version)
    revision = await _revision(session, scene_id, revision_id)
    sections = sections or {"heading", "blocks"}
    if sections - {"heading", "blocks"}:
        raise Invalid("Invalid revision sections")
    await revisions_crud.restore(session, scene, revision, sections)
    await scene_changed(session, project_id, scene, reason="revision.restored")
    return scene


async def diff_revisions(session: AsyncSession, project_id: int, scene_id: int, revision_id: int, other_revision_id: int) -> dict[str, Any]:
    """Return a bounded unified diff between two revisions of a scene."""
    await scene_in_project(session, project_id, scene_id)
    first, second = await _revision(session, scene_id, revision_id), await _revision(session, scene_id, other_revision_id)
    before = json.dumps(first.snapshot, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    after = json.dumps(second.snapshot, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    changes = "\n".join(difflib.unified_diff(before, after, fromfile=f"revision-{revision_id}", tofile=f"revision-{other_revision_id}"))
    if len(changes) > 100_000:
        raise Invalid("Revision diff is too large")
    return {"scene_id": scene_id, "from_revision": revision_id, "to_revision": other_revision_id, "diff": changes}


# --- import ------------------------------------------------------------------------------------


def parse_import(file_format: str, raw: bytes) -> Any:
    """Parse Fountain, FDX or PDF bytes into a screenplay document."""
    from draftpilot.core.screenplay.adapters.pdf import parse_pdf

    if file_format not in {"fountain", "fdx", "pdf"}:
        raise Invalid("Unsupported import format")
    if len(raw) > MAX_IMPORT_BYTES:
        raise Invalid("Import is too large")
    try:
        if file_format == "pdf":
            return parse_pdf(raw)
        text = raw.decode("utf-8-sig")
        return parse_fountain(text) if file_format == "fountain" else parse_fdx(text)
    except (UnicodeDecodeError, ValueError, RuntimeError) as exc:
        raise Invalid("Malformed screenplay import") from exc


async def import_screenplay(
    session: AsyncSession, project_id: int, file_format: str, raw: bytes, source_screenplay_id: int | None = None, title: str | None = None
) -> Screenplay:
    """Import a script as a new draft of the project; existing drafts are never replaced."""
    from draftpilot.core.benchmark import source_digest

    source = await screenplay_in_project(session, project_id, source_screenplay_id)
    document = parse_import(file_format, raw)
    imported = await screenplays_crud.create(
        session,
        ScreenplayCreate(
            project_id=project_id,
            title=(title or f"{source.title} (Imported)")[:200],
            format=source.format,
            status="draft",
            source_sha256=source_digest(raw),
        ),
    )
    assert imported.id is not None
    await save_screenplay_doc(session, imported.id, document)
    await temporal.start_best_effort("reindex_project", project_id, description="Imported screenplay reindex enqueue")
    await temporal.start_best_effort("refresh_story_twin", project_id, description="Story twin refresh enqueue")
    await events.publish(project_id, "structure.changed", {"screenplay_id": imported.id, "reason": "import"})
    return imported


# --- writer twin -------------------------------------------------------------------------------


async def update_writer_profile(session: AsyncSession, changes: dict[str, Any]) -> WriterProfile:
    """Update the writer profile the room writes for."""
    profile = await get_writer_profile(session)
    allowed = set(WriterProfile.model_fields) - {"id", "updated_at"}
    if set(changes) - allowed:
        raise Invalid(f"Unsupported writer profile field; expected some of {', '.join(sorted(allowed))}")
    for key, value in changes.items():
        setattr(profile, key, value)
    profile.updated_at = datetime.now(UTC)
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def add_writer_memory(session: AsyncSession, text: str, kind: str = "preference", project_id: int | None = None, pinned: bool = False) -> WriterMemory:
    """Remember something about how the writer works (optionally for one project)."""
    if not text.strip():
        raise Invalid("A memory needs text")
    if project_id is not None:
        await require_project(session, project_id)
    memory = WriterMemory(kind=kind[:30], text=text[:2000], project_id=project_id, pinned=pinned, source="agent")
    session.add(memory)
    await session.commit()
    await session.refresh(memory)
    return memory


def ensure_pending(status: str) -> None:
    """Raise ``Conflict`` unless a proposal is still pending."""
    if status != "proposed":
        raise Conflict("Proposal is not pending")
