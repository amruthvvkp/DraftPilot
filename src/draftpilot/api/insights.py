"""Usefulness endpoints: how the room is doing for this writer, and the writer's feedback on runs."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.core.usefulness import project_insights
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import workflow_runs as runs_crud
from draftpilot.models import AgentFeedback, AgentFeedbackCreate, AgentRun

router = APIRouter(prefix="/projects/{project_id}", tags=["insights"])


@router.get("/insights")
async def get_insights(project_id: int, session: AsyncSession = Depends(async_get_db)) -> dict[str, Any]:
    """Return acceptance, retention, feedback, cost and reliability per workflow and role."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return await project_insights(session, project_id)


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def give_feedback(
    project_id: int, data: AgentFeedbackCreate, session: AsyncSession = Depends(async_get_db)
) -> dict[str, Any]:
    """Record a thumbs up or down on one agent run or room workflow run."""
    if (data.agent_run_id is None) == (data.workflow_run_id is None):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Give exactly one of agent_run_id or workflow_run_id")
    if data.rating == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Rating must be 1 or -1")
    if data.agent_run_id is not None:
        agent_run = await session.get(AgentRun, data.agent_run_id)
        if agent_run is None or agent_run.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    else:
        run = await runs_crud.get(session, data.workflow_run_id or 0)
        if run is None or run.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    feedback = AgentFeedback(project_id=project_id, **data.model_dump())
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    return feedback.model_dump(mode="json")
