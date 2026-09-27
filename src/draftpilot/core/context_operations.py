"""Shared typed operations for applying reviewed creative context."""

from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.queue import enqueue_best_effort
from draftpilot.crud import knowledge_graph as graph_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.crud import workflow_runs as runs_crud
from draftpilot.models import KnowledgeNode, KnowledgeNodeCreate


async def apply_context_suggestion(
    session: AsyncSession,
    project_id: int,
    run_id: int,
    expected_source_version: int,
) -> KnowledgeNode:
    """Apply one completed context run as a provenance-linked graph node."""
    run = await runs_crud.get(session, run_id)
    if run is None or run.project_id != project_id:
        raise ValueError("Context run not found")
    if run.kind != "context_generation" or run.status != "succeeded" or run.result is None:
        raise ValueError("Context run is not ready to apply")
    if run.result.get("applied_node_id") is not None:
        raise ValueError("Context suggestion was already applied")
    source_version = run.result.get("source_version")
    if source_version != expected_source_version:
        raise ValueError("Source artifact version has changed")
    source_artifact_id = run.input.get("artifact_id")
    if not isinstance(source_artifact_id, int):
        raise ValueError("Context run has no source artifact")
    source_artifact = await artifacts_crud.get(session, source_artifact_id)
    if source_artifact is None or source_artifact.project_id != project_id:
        raise ValueError("Context source artifact not found")
    if source_artifact.version != expected_source_version:
        raise ValueError("Source artifact version has changed")
    suggestion = run.result.get("suggestion")
    output_kind = run.result.get("output_kind")
    if not isinstance(suggestion, str) or not suggestion.strip() or not isinstance(output_kind, str):
        raise ValueError("Context run has no applicable suggestion")
    node = await graph_crud.create_node(
        session,
        KnowledgeNodeCreate(
            project_id=project_id,
            kind=output_kind,
            label=f"{output_kind.replace('_', ' ').title()} from run {run_id}",
            description=suggestion,
            node_metadata={
                "source_run_id": run_id,
                "source_artifact_id": source_artifact_id,
                "source_version": source_version,
                "citations": run.result.get("citations", []),
            },
        ),
    )
    if node.id is not None:
        await enqueue_best_effort(
            "index_rag_document",
            {
                "project_id": project_id,
                "source_id": f"knowledge_node:{node.id}",
                "source_kind": f"knowledge_node:{node.kind}",
                "text": f"{node.label}\n{node.description or ''}",
                "content_version": node.version,
            },
            description="Context suggestion RAG enqueue",
        )
    run.result = {**run.result, "applied_node_id": node.id}
    await runs_crud.update_status(session, run, "applied", result=run.result)
    return node
