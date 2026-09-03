"""Project-scoped Copilot conversation endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.crud import copilot_messages as messages_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.models import CopilotMessageCreate, CopilotMessageRead

router = APIRouter(prefix="/projects/{project_id}/copilot/messages", tags=["copilot"])


class CopilotMessageRequest(BaseModel):
    """Accept one context-bearing Copilot conversation turn."""

    role: str = Field(default="user", pattern="^(user|assistant|system)$")
    content: str = Field(min_length=1, max_length=12000)
    page: str = Field(default="workspace", min_length=1, max_length=100)
    artifact: str | None = Field(default=None, max_length=200)
    selection: str | None = Field(default=None, max_length=2000)
    instruction_layers: dict[str, object] = Field(default_factory=dict)
    citations: list[dict[str, object]] = Field(default_factory=list)
    active_tools: list[str] = Field(default_factory=list)


@router.get("", response_model=list[CopilotMessageRead])
async def list_messages(
    project_id: int, session: AsyncSession = Depends(async_get_db)
) -> list[CopilotMessageRead]:
    """Return the persisted conversation for one project."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    messages = await messages_crud.list_for_project(session, project_id)
    return [CopilotMessageRead.model_validate(message) for message in messages]


@router.post("", response_model=CopilotMessageRead, status_code=status.HTTP_201_CREATED)
async def create_message(
    project_id: int,
    data: CopilotMessageRequest,
    session: AsyncSession = Depends(async_get_db),
) -> CopilotMessageRead:
    """Persist one Copilot turn with its supplied context envelope."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    message = await messages_crud.create(
        session,
        CopilotMessageCreate(
            project_id=project_id,
            **data.model_dump(),
        ),
    )
    return CopilotMessageRead.model_validate(message)
