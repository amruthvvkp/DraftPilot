"""Writers' room endpoints: AG-UI agent chat and its threads, room workflows, and measured agent runs."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest
from pydantic_ai.ui.ag_ui import AGUIAdapter
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.agents.chat import dump_thread, stream_room_chat
from draftpilot.agents.context import load_room_context
from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.models import describe_model
from draftpilot.agents.runtime import chat_agents
from draftpilot.agents.specs import role_spec
from draftpilot.agents.workflow_runner import create_room_workflow_run
from draftpilot.agents.workflows import ROOM_WORKFLOWS
from draftpilot.core import temporal
from draftpilot.core.agent_roles import normalize_agent_role, normalize_permission_mode
from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.copilot import retrieve_context
from draftpilot.core.db import async_get_db
from draftpilot.core.providers import settings_from_profile
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import provider_profiles as profiles_crud
from draftpilot.models import (
    AgentRun,
    AgentRunRead,
    ChatThread,
    ChatThreadRead,
    WorkflowRunRead,
)

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


def _option(run_input: Any, name: str, default: Any = None) -> Any:
    """Read a chat option from AG-UI ``forwardedProps`` first, then ``state``."""
    for source in (getattr(run_input, "forwarded_props", None), getattr(run_input, "state", None)):
        if isinstance(source, dict) and source.get(name) not in (None, ""):
            return source[name]
    return default


@router.post("/chat")
async def room_chat(project_id: int, request: Request, session: AsyncSession = Depends(async_get_db)) -> StreamingResponse:
    """Stream one chat turn from a room role over the AG-UI protocol.

    ``forwardedProps`` (or ``state``) carry ``role``, ``permission_mode``, ``provider_profile_id``,
    and the writer's focus: ``page``, ``artifact``, ``selection``, ``scene_id``. ``threadId`` names
    the conversation, which the server keeps.
    """
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        run_input = AGUIAdapter.build_run_input(await request.body())
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid AG-UI run input") from exc
    role = normalize_agent_role(str(_option(run_input, "role", "showrunner")))
    profile = _option(run_input, "provider_profile_id")
    provider_profile_id = int(profile) if profile is not None else None
    config = await resolve_llm(session, provider_profile_id)
    if not config.enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No LLM provider is enabled")
    try:
        model_ref = await describe_model(provider_profile_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Model provider unavailable: {exc}"
        ) from exc
    spec = role_spec(role)
    adapter = AGUIAdapter(agent=chat_agents()[spec.key], run_input=run_input, accept=request.headers.get("accept"))
    thread = await session.get(ChatThread, run_input.thread_id) if run_input.thread_id else None
    if thread is not None and thread.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    if thread is not None and thread.messages:
        # The server's copy of the thread is authoritative; only the writer's newest message is taken from the client.
        stored = ModelMessagesTypeAdapter.validate_python(thread.messages)
        latest = adapter.messages[-1:] if adapter.messages and isinstance(adapter.messages[-1], ModelRequest) else []
        adapter.__dict__["messages"] = stored if adapter.deferred_tool_results else [*stored, *latest]
    scene = _option(run_input, "scene_id")
    context = await load_room_context(session, project_id)
    deps = RoomDeps(
        project_id=project_id,
        page=str(_option(run_input, "page", "studio")),
        artifact=_option(run_input, "artifact"),
        selection=_option(run_input, "selection"),
        scene_id=int(scene) if scene is not None else None,
        permission_mode=normalize_permission_mode(str(_option(run_input, "permission_mode", "suggest"))),
        project_instruction=context.project_instruction,
        writer_brief=context.writer_brief,
        story_brief=context.story_brief,
    )
    await session.close()
    try:
        return await stream_room_chat(
            request, spec=spec, model_ref=model_ref, deps_without_context=deps, retrieve=retrieve_context, adapter=adapter
        )
    except (ConnectionError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Temporal is unavailable: {exc}") from exc


class ThreadRename(BaseModel):
    """Rename a chat thread."""

    title: str = Field(min_length=1, max_length=200)


@router.get("/threads", response_model=list[ChatThreadRead])
async def list_threads(project_id: int, session: AsyncSession = Depends(async_get_db)) -> list[ChatThreadRead]:
    """List the project's chat threads, most recent first."""
    rows = await session.exec(
        select(ChatThread).where(ChatThread.project_id == project_id).order_by(col(ChatThread.updated_at).desc())
    )
    return [ChatThreadRead.model_validate(row, from_attributes=True) for row in rows.all()]


async def _thread(session: AsyncSession, project_id: int, thread_id: str) -> ChatThread:
    """Return a thread of the project or raise 404."""
    thread = await session.get(ChatThread, thread_id)
    if thread is None or thread.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return thread


@router.get("/threads/{thread_id}")
async def read_thread(project_id: int, thread_id: str, session: AsyncSession = Depends(async_get_db)) -> dict[str, Any]:
    """Return a thread and its messages in AG-UI form, to reopen the conversation."""
    thread = await _thread(session, project_id, thread_id)
    return {**ChatThreadRead.model_validate(thread, from_attributes=True).model_dump(mode="json"), "messages": dump_thread(thread)}


@router.patch("/threads/{thread_id}", response_model=ChatThreadRead)
async def rename_thread(
    project_id: int, thread_id: str, data: ThreadRename, session: AsyncSession = Depends(async_get_db)
) -> ChatThreadRead:
    """Rename a thread."""
    thread = await _thread(session, project_id, thread_id)
    thread.title = data.title
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return ChatThreadRead.model_validate(thread, from_attributes=True)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(project_id: int, thread_id: str, session: AsyncSession = Depends(async_get_db)) -> None:
    """Delete a thread and its history."""
    await session.delete(await _thread(session, project_id, thread_id))
    await session.commit()


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
    await temporal.start_run(run.id)
    return WorkflowRunRead.model_validate(run)
