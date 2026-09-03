"""ARQ background tasks.

``analyze_screenplay`` computes deterministic structural metrics for a
screenplay and, when an LLM provider is configured, augments them with a short
qualitative note via a PydanticAI agent. Results are cached in Redis so the UI
can display them. The LLM step is fully optional — the task always returns the
deterministic metrics even when no model is reachable.
"""

import httpx
import logfire

from draftpilot.core.cache import cache_set
from draftpilot.core.config import settings
from draftpilot.core.db import session_scope
from draftpilot.core.providers import create_chat_model
from draftpilot.core.agent_roles import normalize_agent_role
from draftpilot.core.copilot import generate_reply, retrieve_context
from draftpilot.core.providers import settings_from_profile
from draftpilot.crud import copilot_messages as messages_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import workflow_runs as workflow_runs_crud
from draftpilot.crud import provider_profiles as profiles_crud
from draftpilot.models import CopilotMessageCreate, WorkflowRun

ANALYSIS_CACHE_KEY = "analysis:{id}"


async def _llm_note(title: str, scene_count: int, word_count: int, agent_role: str) -> str | None:
    """Optional one-line qualitative note from a PydanticAI agent."""
    if not settings.llm.enabled:
        return None
    try:
        from pydantic_ai import Agent
        model = create_chat_model(settings.llm)
        agent = Agent(
            model,
            system_prompt=(
                f"You are the {agent_role.replace('_', ' ')}. Given basic stats about a screenplay, "
                "reply with a single concise sentence of constructive feedback."
            ),
        )
        result = await agent.run(
            f"Title: {title}. Scenes: {scene_count}. Words: {word_count}."
        )
        return result.output
    except Exception as exc:  # pragma: no cover - provider/network dependent
        logfire.warning("LLM note skipped: {exc}", exc=str(exc))
        return None


async def analyze_screenplay(ctx: dict, screenplay_id: int, agent_role: str = "story_architect") -> dict:
    """Compute metrics for a screenplay and cache the result in Redis."""
    with logfire.span("analyze_screenplay", screenplay_id=screenplay_id):
        async with session_scope() as session:
            screenplay = await screenplays_crud.get(session, screenplay_id)
            if screenplay is None:
                logfire.warning("Screenplay {id} not found", id=screenplay_id)
                return {"error": "not_found"}
            scenes = await scenes_crud.list_for_screenplay(session, screenplay_id)
            title = screenplay.title

        scene_count = len(scenes)
        word_count = sum(len(s.body.split()) for s in scenes)
        avg_scene_words = round(word_count / scene_count, 1) if scene_count else 0

        result: dict = {
            "scene_count": scene_count,
            "word_count": word_count,
            "avg_scene_words": avg_scene_words,
            "estimated_pages": round(word_count / 190, 1),  # ~190 words/page heuristic
        }

        note = await _llm_note(title, scene_count, word_count, agent_role)
        if note:
            result["note"] = note

        await cache_set(ANALYSIS_CACHE_KEY.format(id=screenplay_id), result, ttl=3600)
        logfire.info("Analysis complete for {id}: {result}", id=screenplay_id, result=result)
        return result


async def index_rag_document(ctx: dict, document: dict[str, object]) -> dict[str, str]:
    """Index one approved document through the isolated RAG HTTP boundary."""
    project_id = document.get("project_id")
    if not isinstance(project_id, int):
        return {"error": "project_id is required"}
    payload = {
        "source_id": document.get("source_id"),
        "source_kind": document.get("source_kind"),
        "text": document.get("text"),
        "content_version": document.get("content_version"),
    }
    headers = {"Authorization": f"Bearer {settings.rag.auth_token.get_secret_value()}"}
    url = f"{settings.rag.service_url.rstrip('/')}/projects/{project_id}/documents"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
    return {"status": "indexed"}


async def execute_workflow(ctx: dict, run_id: int) -> dict:
    """Resume a persisted workflow run and record its terminal state."""
    with logfire.span("execute_workflow", run_id=run_id):
        async with session_scope() as session:
            run = await workflow_runs_crud.get(session, run_id)
            if run is None:
                return {"error": "not_found"}
            await workflow_runs_crud.update_status(session, run, "running")
            copilot_run = run.kind == "copilot_response"
            screenplay_id = run.input.get("screenplay_id")
            if not copilot_run and not isinstance(screenplay_id, int):
                await workflow_runs_crud.update_status(
                    session, run, "failed", error="screenplay_id is required"
                )
                return {"error": "invalid_input"}
        if copilot_run:
            return await _execute_copilot_run(ctx, run)
        assert isinstance(screenplay_id, int)
        try:
            result = await analyze_screenplay(ctx, screenplay_id, run.agent_role)
        except Exception as exc:  # pragma: no cover - worker failure boundary
            async with session_scope() as session:
                run = await workflow_runs_crud.get(session, run_id)
                if run is not None:
                    await workflow_runs_crud.update_status(session, run, "failed", error=str(exc))
            raise
        async with session_scope() as session:
            run = await workflow_runs_crud.get(session, run_id)
            if run is not None and run.status != "cancelled":
                await workflow_runs_crud.update_status(session, run, "succeeded", result=result)
                return result
        return {"status": "cancelled"}


async def _execute_copilot_run(ctx: dict, run: WorkflowRun) -> dict[str, object]:
    """Resume one persisted Copilot response and store its assistant turn."""
    data = run.input
    content = data.get("content")
    page = data.get("page")
    history = data.get("history", [])
    if not isinstance(content, str) or not isinstance(page, str) or not isinstance(history, list):
        async with session_scope() as session:
            current = await workflow_runs_crud.get(session, run.id or 0)
            if current is not None:
                await workflow_runs_crud.update_status(session, current, "failed", error="invalid Copilot input")
        return {"error": "invalid_input"}
    try:
        llm_settings = None
        profile_id = data.get("provider_profile_id")
        if isinstance(profile_id, int):
            async with session_scope() as session:
                profile = await profiles_crud.get(session, profile_id)
                if profile is None:
                    raise ValueError("Provider profile not found")
                llm_settings = settings_from_profile(profile)
        retrieved_context = await retrieve_context(run.project_id, content)
        raw_citations = data.get("citations")
        citations = raw_citations if isinstance(raw_citations, list) else []
        reply = await generate_reply(
            content,
            page,
            data.get("artifact") if isinstance(data.get("artifact"), str) else None,
            data.get("selection") if isinstance(data.get("selection"), str) else None,
            normalize_agent_role(run.agent_role),
            history,
            llm_settings,
            retrieved_context,
        )
    except Exception as exc:  # pragma: no cover - provider/network dependent
        async with session_scope() as session:
            current = await workflow_runs_crud.get(session, run.id or 0)
            if current is not None:
                await workflow_runs_crud.update_status(session, current, "failed", error=str(exc))
        raise
    async with session_scope() as session:
        current = await workflow_runs_crud.get(session, run.id or 0)
        if current is None or current.status == "cancelled":
            return {"status": "cancelled"}
        assistant = await messages_crud.create(
            session,
            CopilotMessageCreate(
                project_id=current.project_id,
                role="assistant",
                content=reply,
                page=page,
                artifact=data.get("artifact") if isinstance(data.get("artifact"), str) else None,
                selection=data.get("selection") if isinstance(data.get("selection"), str) else None,
                instruction_layers=data.get("instruction_layers") if isinstance(data.get("instruction_layers"), dict) else {"agent_role": current.agent_role, "permission_mode": current.permission_mode},
                citations=citations
                + [item["citation"] for item in retrieved_context if isinstance(item.get("citation"), dict)],
                active_tools=data.get("active_tools") if isinstance(data.get("active_tools"), list) else [],
            ),
        )
        await workflow_runs_crud.update_status(
            session,
            current,
            "succeeded",
            result={"assistant_message_id": assistant.id},
        )
        return {"assistant_message_id": assistant.id}
