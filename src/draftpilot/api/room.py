"""Writers' room endpoints: streamed agent chat and measured agent runs."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.agents.chat import stream_room_chat
from draftpilot.agents.context import load_room_context
from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.specs import role_spec
from draftpilot.core.agent_roles import normalize_agent_role, normalize_permission_mode
from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.copilot import retrieve_context
from draftpilot.core.db import async_get_db
from draftpilot.core.providers import build_chat_model, settings_from_profile
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import provider_profiles as profiles_crud
from draftpilot.models import AgentRun, AgentRunRead

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
