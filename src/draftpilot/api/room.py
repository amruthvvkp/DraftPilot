"""Writers' room endpoints: streamed agent chat, room workflows, and measured agent runs."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.agents.chat import stream_room_chat
from draftpilot.agents.context import load_room_context
from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.specs import role_spec
from draftpilot.agents.workflow_runner import create_room_workflow_run
from draftpilot.agents.workflows import ROOM_WORKFLOWS
from draftpilot.core.agent_roles import normalize_agent_role, normalize_permission_mode
from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.copilot import retrieve_context
from draftpilot.core.db import async_get_db
from draftpilot.core.providers import build_chat_model, settings_from_profile
from draftpilot.core.queue import get_arq_pool
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import provider_profiles as profiles_crud
from draftpilot.models import AgentRun, AgentRunRead, WorkflowRunRead

router = APIRouter(prefix="/projects/{project_id}/room", tags=["room"])


async def resolve_llm(session: AsyncSession, provider_profile_id: int | None) -> LLMSettings:
    """Return the selected provider profile's settings, or the installation default."""
    if provider_profile_id is None:
        return settings.llm
    profile = await profiles_crud.get(session, provider_profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider profile not found")
    try:
        return settings_from_profile(profile)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/chat")
async def room_chat(
    project_id: int,
    request: Request,
    role: str = "story_architect",
    permission_mode: str = "chat_only",
    provider_profile_id: int | None = None,
    page: str = "studio",
    artifact: str | None = None,
    selection: str | None = None,
    scene_id: int | None = None,
    session: AsyncSession = Depends(async_get_db),
) -> StreamingResponse:
    """Stream one chat turn from a room role (Vercel AI SDK v6 UI-message stream)."""
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    config = await resolve_llm(session, provider_profile_id)
    if not config.enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No LLM provider is enabled")
    try:
        model, model_name = await build_chat_model(config)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Model provider unavailable: {exc}"
        ) from exc
    context = await load_room_context(session, project_id)
    deps = RoomDeps(
        project_id=project_id,
        page=page,
        artifact=artifact,
        selection=selection,
        scene_id=scene_id,
        permission_mode=normalize_permission_mode(permission_mode),
        project_instruction=context.project_instruction,
        writer_brief=context.writer_brief,
        story_brief=context.story_brief,
    )
    await session.close()
    return await stream_room_chat(
        request,
        spec=role_spec(normalize_agent_role(role)),
        model=model,
        deps_without_context=deps,
        provider=config.provider,
        model_name=model_name,
        retrieve=retrieve_context,
    )


@router.get("/runs", response_model=list[AgentRunRead])
async def list_agent_runs(
    project_id: int, limit: int = 50, session: AsyncSession = Depends(async_get_db)
) -> list[AgentRunRead]:
    """List a project's most recent measured agent runs."""
    result = await session.exec(
        select(AgentRun)
        .where(AgentRun.project_id == project_id)
        .order_by(col(AgentRun.id).desc())
        .limit(max(1, min(limit, 200)))
    )
    return [AgentRunRead.model_validate(run, from_attributes=True) for run in result.all()]


class RoomWorkflowInfo(BaseModel):
    """Describe one room workflow for the studio's launcher."""

    key: str
    label: str
    description: str
    roles: list[str]
    proposes: bool
    params_schema: dict[str, Any]


class RoomWorkflowStart(BaseModel):
    """Start one room workflow with its parameters."""

    workflow: str = Field(min_length=1, max_length=60)
    params: dict[str, Any] = Field(default_factory=dict)
    provider_profile_id: int | None = None


@router.get("/workflows", response_model=list[RoomWorkflowInfo])
async def list_room_workflows(project_id: int) -> list[RoomWorkflowInfo]:
    """List the room workflows with each one's parameter schema."""
    return [
        RoomWorkflowInfo(
            key=workflow.key,
            label=workflow.label,
            description=workflow.description,
            roles=list(workflow.roles),
            proposes=workflow.proposes,
            params_schema=workflow.params.model_json_schema(),
        )
        for workflow in ROOM_WORKFLOWS.values()
    ]


@router.post("/workflows", response_model=WorkflowRunRead, status_code=status.HTTP_202_ACCEPTED)
async def start_room_workflow(
    project_id: int, data: RoomWorkflowStart, session: AsyncSession = Depends(async_get_db)
) -> WorkflowRunRead:
    """Validate, persist, and enqueue one room workflow run; its results arrive as proposals or a report."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        run = await create_room_workflow_run(session, project_id, data.workflow, data.params, data.provider_profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown room workflow") from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.errors(include_url=False, include_context=False)
        ) from exc
    await (await get_arq_pool()).enqueue_job("execute_workflow", run.id)
    return WorkflowRunRead.model_validate(run)
