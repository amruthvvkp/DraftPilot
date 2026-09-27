"""Project-scoped Copilot conversation endpoints."""

from typing import Any

import logfire
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.agent_roles import normalize_agent_role, normalize_permission_mode
from draftpilot.core.capabilities import capabilities_for_page
from draftpilot.core.config import LLMSettings
from draftpilot.core.copilot import generate_reply, retrieve_context
from draftpilot.core.db import async_get_db
from draftpilot.core.providers import settings_from_profile
from draftpilot.core.queue import get_arq_pool
from draftpilot.crud import copilot_messages as messages_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import provider_profiles as profiles_crud
from draftpilot.crud import workflow_runs as runs_crud
from draftpilot.models import (
    CopilotMessageCreate,
    CopilotMessageRead,
    WorkflowRunCreate,
    WorkflowRunRead,
)

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


def _server_context(data: CopilotMessageRequest) -> CopilotMessageRequest:
    """Replace client-supplied active tools with the page-scoped server catalog."""
    return data.model_copy(update={"active_tools": capabilities_for_page(data.page)})


async def _selected_profile_config(
    data: CopilotMessageRequest, session: AsyncSession
) -> tuple[int | None, LLMSettings | None]:
    """Resolve an optional server-side provider profile selected for a turn."""
    raw_profile_id = data.instruction_layers.get("provider_profile_id")
    if not isinstance(raw_profile_id, int):
        return None, None
    profile = await profiles_crud.get(session, raw_profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider profile not found")
    try:
        return raw_profile_id, settings_from_profile(profile)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


class CopilotRunResponse(BaseModel):
    """Return the persisted user turn and its reconnectable workflow run."""

    message: CopilotMessageRead
    run: WorkflowRunRead


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
    data = _server_context(data)
    message = await messages_crud.create(
        session,
        CopilotMessageCreate(
            project_id=project_id,
            **data.model_dump(),
        ),
    )
    return CopilotMessageRead.model_validate(message)


@router.post("/respond", response_model=CopilotMessageRead, status_code=status.HTTP_201_CREATED)
async def respond_to_message(
    project_id: int,
    data: CopilotMessageRequest,
    session: AsyncSession = Depends(async_get_db),
) -> CopilotMessageRead:
    """Persist a user turn and return a provider-backed assistant response."""
    if data.role != "user":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Response input must be a user turn")
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    data = _server_context(data)
    _, profile_config = await _selected_profile_config(data, session)
    retrieved_context = await retrieve_context(project_id, data.content)
    citations: list[dict[str, Any]] = [dict(item) for item in data.citations] + [
        citation for item in retrieved_context if isinstance(citation := item.get("citation"), dict)
    ]
    data = data.model_copy(update={"citations": citations})
    await messages_crud.create(session, CopilotMessageCreate(project_id=project_id, **data.model_dump()))
    history = [
        {"role": message.role, "content": message.content}
        for message in await messages_crud.list_for_project(session, project_id)
    ]
    role = normalize_agent_role(data.instruction_layers.get("agent_role"))
    try:
        reply = await generate_reply(
            data.content, data.page, data.artifact, data.selection, role, history, profile_config,
            retrieved_context,
            project_id=project_id,
            permission_mode=normalize_permission_mode(data.instruction_layers.get("permission_mode")),
        )
    except Exception as exc:
        logfire.warning("Copilot response unavailable: {exc}", exc=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configured Copilot provider is unavailable",
        ) from exc
    assistant = await messages_crud.create(
        session,
        CopilotMessageCreate(
            project_id=project_id,
            role="assistant",
            content=reply,
            page=data.page,
            artifact=data.artifact,
            selection=data.selection,
            instruction_layers=data.instruction_layers,
            citations=citations,
            active_tools=data.active_tools,
        ),
    )
    return CopilotMessageRead.model_validate(assistant)


@router.post("/respond-async", response_model=CopilotRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_async_response(
    project_id: int,
    data: CopilotMessageRequest,
    session: AsyncSession = Depends(async_get_db),
) -> CopilotRunResponse:
    """Persist a Copilot turn and enqueue a reconnectable provider response."""
    if data.role != "user":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Response input must be a user turn")
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    data = _server_context(data)
    retrieved_context = await retrieve_context(project_id, data.content)
    data = data.model_copy(update={
        "citations": data.citations + [
            item["citation"] for item in retrieved_context if isinstance(item.get("citation"), dict)
        ]
    })
    message = await messages_crud.create(
        session,
        CopilotMessageCreate(project_id=project_id, **data.model_dump()),
    )
    profile_id, _ = await _selected_profile_config(data, session)
    history = [
        {"role": item.role, "content": item.content}
        for item in await messages_crud.list_for_project(session, project_id)
    ][:-1]
    role = normalize_agent_role(data.instruction_layers.get("agent_role"))
    permission = normalize_permission_mode(data.instruction_layers.get("permission_mode"))
    run = await runs_crud.create(
        session,
        WorkflowRunCreate(
            project_id=project_id,
            kind="copilot_response",
            input={
                "message_id": message.id,
                "content": data.content,
                "page": data.page,
                "artifact": data.artifact,
                "selection": data.selection,
                "history": history[-12:],
                "instruction_layers": data.instruction_layers,
                "citations": data.citations,
                "active_tools": data.active_tools,
                "retrieved_context": retrieved_context,
                "provider_profile_id": profile_id,
            },
            agent_role=role,
            permission_mode=permission,
        ),
    )
    await (await get_arq_pool()).enqueue_job("execute_workflow", run.id)
    return CopilotRunResponse(
        message=CopilotMessageRead.model_validate(message),
        run=WorkflowRunRead.model_validate(run),
    )
