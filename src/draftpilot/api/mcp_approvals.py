"""Writer-facing review of pending MCP approval requests."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.crud import mcp_access as access_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.models import MCPApprovalRequestRead

router = APIRouter(prefix="/projects/{project_id}/mcp-approvals", tags=["mcp-approvals"])


async def _require_project(session: AsyncSession, project_id: int) -> None:
    """Raise 404 when the project does not exist."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get("", response_model=list[MCPApprovalRequestRead])
async def list_approvals(
    project_id: int, state: str | None = None, session: AsyncSession = Depends(async_get_db)
) -> list[MCPApprovalRequestRead]:
    """List a project's MCP approval requests, optionally filtered by status."""
    await _require_project(session, project_id)
    requests = await access_crud.list_approvals(session, project_id, state)
    return [MCPApprovalRequestRead.model_validate(item, from_attributes=True) for item in requests]


async def _decide(
    session: AsyncSession, project_id: int, approval_id: int, approve: bool
) -> MCPApprovalRequestRead:
    """Record one writer decision and map domain errors to HTTP responses."""
    await _require_project(session, project_id)
    try:
        request = await access_crud.decide_approval(session, project_id, approval_id, approve)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return MCPApprovalRequestRead.model_validate(request, from_attributes=True)


@router.post("/{approval_id}/approve", response_model=MCPApprovalRequestRead)
async def approve(
    project_id: int, approval_id: int, session: AsyncSession = Depends(async_get_db)
) -> MCPApprovalRequestRead:
    """Approve one pending MCP request so its client may retry the call once."""
    return await _decide(session, project_id, approval_id, approve=True)


@router.post("/{approval_id}/reject", response_model=MCPApprovalRequestRead)
async def reject(
    project_id: int, approval_id: int, session: AsyncSession = Depends(async_get_db)
) -> MCPApprovalRequestRead:
    """Reject one pending MCP request; its client can never run that call."""
    return await _decide(session, project_id, approval_id, approve=False)
