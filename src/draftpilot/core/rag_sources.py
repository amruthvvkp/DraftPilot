"""Enumerate every retrievable document a project holds, for a full re-index."""

from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.screenplay.hydrate import scene_text
from draftpilot.crud import blocks as blocks_crud
from draftpilot.crud import knowledge_graph as graph_crud
from draftpilot.crud import project_references as references_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import story_artifacts as artifacts_crud


async def project_documents(session: AsyncSession, project_id: int) -> list[dict[str, object]]:
    """Return index payloads for scenes, artifacts, canon nodes, and references."""
    documents: list[dict[str, object]] = []
    for screenplay in await screenplays_crud.list_for_project(session, project_id):
        scenes = await scenes_crud.list_for_screenplay(session, screenplay.id or 0)
        blocks = await blocks_crud.list_for_scenes(session, [scene.id for scene in scenes if scene.id is not None])
        by_scene: dict[int, list] = {}
        for block in blocks:
            by_scene.setdefault(block.scene_id, []).append(block)
        for scene in scenes:
            text = scene_text(scene.heading, by_scene.get(scene.id or 0, []))
            if text.strip():
                documents.append(
                    {"source_id": f"scene:{scene.id}", "source_kind": "scene", "text": text, "content_version": scene.version}
                )
    for artifact in await artifacts_crud.list_for_project(session, project_id):
        if artifact.content.strip() or artifact.title.strip():
            documents.append(
                {
                    "source_id": f"artifact:{artifact.id}",
                    "source_kind": artifact.kind,
                    "text": f"{artifact.title}\n{artifact.content}".strip(),
                    "content_version": artifact.version,
                }
            )
    for node in await graph_crud.list_nodes(session, project_id):
        documents.append(
            {
                "source_id": f"knowledge_node:{node.id}",
                "source_kind": f"knowledge_node:{node.kind}",
                "text": f"{node.label}\n{node.description or ''}".strip(),
                "content_version": node.version,
            }
        )
    for reference in await references_crud.list_for_project(session, project_id):
        documents.append(
            {
                "source_id": f"reference:{reference.id}",
                "source_kind": "reference",
                "text": f"{reference.label}\n{reference.note or ''}".strip(),
                "content_version": reference.version,
            }
        )
    return documents
