"""Versioned endpoints for project-scoped Monty audit records and read-only script analysis."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.continuity_rules import check_continuity_rules
from draftpilot.core.db import async_get_db
from draftpilot.core.monty import MontyDisabledError, MontySandboxError
from draftpilot.core.script_analysis import analyze_script
from draftpilot.crud import monty_executions as executions_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.models import MontyExecutionRead

router = APIRouter(prefix="/projects/{project_id}/monty-executions", tags=["monty"])
analysis_router = APIRouter(prefix="/projects/{project_id}", tags=["monty"])


class AnalyzeScriptRequest(BaseModel):
    """Read-only analysis code to run over the project's ``script`` and ``story`` views."""

    code: str = Field(min_length=1)


class ContinuityRulesRequest(BaseModel):
    """Which scenes' findings to keep (all when empty)."""

    scene_ids: list[int] = Field(default_factory=list, max_length=200)


async def _require_project(session: AsyncSession, project_id: int) -> None:
    """Raise 404 unless the project exists."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _sandbox_error(exc: MontyDisabledError | MontySandboxError) -> HTTPException:
    """Map a refused or failed execution to 409 (disabled) or 422 (the code failed)."""
    if isinstance(exc, MontyDisabledError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    detail = f"{exc}: {exc.detail}" if exc.detail else str(exc)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


@router.get("", response_model=list[MontyExecutionRead])
async def list_monty_executions(
    project_id: int, session: AsyncSession = Depends(async_get_db)
) -> list[MontyExecutionRead]:
    """Return redacted Monty audit records for one project."""
    await _require_project(session, project_id)
    records = await executions_crud.list_for_project(session, project_id)
    return [MontyExecutionRead.model_validate(record) for record in records]


@analysis_router.post("/analyze-script")
async def analyze_project_script(
    project_id: int, body: AnalyzeScriptRequest, session: AsyncSession = Depends(async_get_db)
) -> dict[str, Any]:
    """Run read-only analysis code over the script and Story twin in Monty (audited)."""
    await _require_project(session, project_id)
    try:
        result = await analyze_script(session, project_id, body.code)
    except (MontyDisabledError, MontySandboxError) as exc:
        raise _sandbox_error(exc) from exc
    return {"value": result.value, "stdout": result.stdout, "duration_ms": result.duration_ms}


@analysis_router.post("/continuity-rules")
async def run_continuity_rules(
    project_id: int, body: ContinuityRulesRequest, session: AsyncSession = Depends(async_get_db)
) -> dict[str, Any]:
    """Run the built-in continuity rules over the script and Story twin in Monty (audited)."""
    await _require_project(session, project_id)
    try:
        return await check_continuity_rules(session, project_id, body.scene_ids or None)
    except (MontyDisabledError, MontySandboxError) as exc:
        raise _sandbox_error(exc) from exc
