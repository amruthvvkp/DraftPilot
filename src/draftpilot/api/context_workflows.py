"""Project-scoped context-generation workflow endpoints."""

import logfire
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.context_workflows import (
    ContextWorkflowRequest,
    ContextWorkflowSpec,
    context_workflow_catalog,
    get_context_workflow,
    validate_context_source,
)
from draftpilot.core.db import async_get_db
from draftpilot.core.queue import get_arq_pool
from draftpilot.crud import knowledge_graph as graph_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.crud import workflow_runs as runs_crud
from draftpilot.models import KnowledgeNodeCreate, KnowledgeNodeRead, WorkflowRunCreate, WorkflowRunRead

router = APIRouter(prefix="/projects/{project_id}/context/workflows", tags=["context-workflows"])


class ApplyContextSuggestionRequest(BaseModel):
    """Confirm a review-only suggestion and preserve its source version."""

    expected_source_version: int = Field(ge=1)


@router.get("", response_model=list[ContextWorkflowSpec])
def list_context_workflows() -> list[ContextWorkflowSpec]:
    """List the available typed context-generation workflows."""
    return context_workflow_catalog()


@router.post("/runs", response_model=WorkflowRunRead, status_code=status.HTTP_202_ACCEPTED)
async def start_context_workflow(
    project_id: int,
    data: ContextWorkflowRequest,
    session: AsyncSession = Depends(async_get_db),
) -> WorkflowRunRead:
    """Persist and enqueue a citation-bearing, review-only context generation run."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    workflow = get_context_workflow(data.workflow)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unknown context workflow")
    source_version: int | None = None
    source_kind: str | None = None
    if data.artifact_id is not None:
        artifact = await artifacts_crud.get(session, data.artifact_id)
        if artifact is None or artifact.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Context artifact not found")
        try:
            validate_context_source(workflow, artifact.kind)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        source_version = artifact.version
        source_kind = artifact.kind
    elif workflow.input_artifact_kinds:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="This workflow requires a source artifact")
    run = await runs_crud.create(
        session,
        WorkflowRunCreate(
            project_id=project_id,
            kind="context_generation",
            input={
                "workflow": workflow.key,
                "instruction": data.instruction,
                "artifact_id": data.artifact_id,
                "source_kind": source_kind,
                "source_version": source_version,
                "output_kind": workflow.output_kind,
                "evaluator": workflow.evaluator,
            },
            agent_role=workflow.agent_role,
            permission_mode=data.permission_mode,
        ),
    )
    await (await get_arq_pool()).enqueue_job("execute_workflow", run.id)
    return WorkflowRunRead.model_validate(run)


@router.post("/runs/{run_id}/apply", response_model=KnowledgeNodeRead)
async def apply_context_suggestion(
    project_id: int,
    run_id: int,
    data: ApplyContextSuggestionRequest,
    session: AsyncSession = Depends(async_get_db),
) -> KnowledgeNodeRead:
    """Apply one completed context suggestion as a provenance-linked graph node."""
    run = await runs_crud.get(session, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Context run not found")
    if run.kind != "context_generation" or run.status != "succeeded" or run.result is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Context run is not ready to apply")
    if run.result.get("applied_node_id") is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Context suggestion was already applied")
    source_version = run.result.get("source_version")
    if source_version != data.expected_source_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source artifact version has changed")
    suggestion = run.result.get("suggestion")
    output_kind = run.result.get("output_kind")
    if not isinstance(suggestion, str) or not suggestion.strip() or not isinstance(output_kind, str):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Context run has no applicable suggestion")
    node = await graph_crud.create_node(
        session,
        KnowledgeNodeCreate(
            project_id=project_id,
            kind=output_kind,
            label=f"{output_kind.replace('_', ' ').title()} from run {run_id}",
            description=suggestion,
            node_metadata={
                "source_run_id": run_id,
                "source_artifact_id": run.input.get("artifact_id"),
                "source_version": source_version,
                "citations": run.result.get("citations", []),
            },
        ),
    )
    if node.id is not None:
        try:
            await (await get_arq_pool()).enqueue_job(
                "index_rag_document",
                {
                    "project_id": project_id,
                    "source_id": f"knowledge_node:{node.id}",
                    "source_kind": f"knowledge_node:{node.kind}",
                    "text": f"{node.label}\n{node.description or ''}",
                    "content_version": node.version,
                },
            )
        except Exception as exc:  # pragma: no cover - queue availability varies by deployment
            logfire.warning("Context suggestion RAG enqueue skipped: {exc}", exc=str(exc))
    run.result = {**run.result, "applied_node_id": node.id}
    await runs_crud.update_status(session, run, "applied", result=run.result)
    return KnowledgeNodeRead.model_validate(node)
