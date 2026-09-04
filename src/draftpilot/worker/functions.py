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
from draftpilot.core.queue import get_arq_pool
from draftpilot.core.providers import create_chat_model
from draftpilot.core.agent_roles import normalize_agent_role
from draftpilot.core.copilot import generate_reply, retrieve_context
from draftpilot.core.providers import settings_from_profile
from draftpilot.core.context_workflows import get_context_workflow
from draftpilot.crud import copilot_messages as messages_crud
from draftpilot.crud import evaluations as evaluations_crud
from draftpilot.crud import blocks as blocks_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import workflow_runs as workflow_runs_crud
from draftpilot.crud import provider_profiles as profiles_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.models import CopilotMessageCreate, EvaluationResult, WorkflowRun

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


async def delete_rag_document(ctx: dict, document: dict[str, object]) -> dict[str, str]:
    """Delete one approved document through the isolated RAG HTTP boundary."""
    project_id = document.get("project_id")
    source_id = document.get("source_id")
    if not isinstance(project_id, int) or not isinstance(source_id, str) or not source_id:
        return {"error": "project_id and source_id are required"}
    headers = {"Authorization": f"Bearer {settings.rag.auth_token.get_secret_value()}"}
    url = f"{settings.rag.service_url.rstrip('/')}/projects/{project_id}/documents/{source_id}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.delete(url, headers=headers)
        response.raise_for_status()
    return {"status": "deleted"}


async def execute_workflow(ctx: dict, run_id: int) -> dict:
    """Resume a persisted workflow run and record its terminal state."""
    with logfire.span("execute_workflow", run_id=run_id):
        async with session_scope() as session:
            run = await workflow_runs_crud.get(session, run_id)
            if run is None:
                return {"error": "not_found"}
            if run.status in {"succeeded", "cancelled"}:
                return {"status": run.status}
            if run.attempt_count >= run.max_attempts:
                await workflow_runs_crud.update_status(
                    session, run, "failed", error="Maximum workflow attempts exceeded"
                )
                return {"error": "maximum_attempts_exceeded"}
            run.attempt_count += 1
            await workflow_runs_crud.update_status(session, run, "running")
            copilot_run = run.kind == "copilot_response"
            evaluation_run = run.kind == "evaluation"
            context_run = run.kind == "context_generation"
            screenplay_id = run.input.get("screenplay_id")
            if not copilot_run and not isinstance(screenplay_id, int):
                await workflow_runs_crud.update_status(
                    session, run, "failed", error="screenplay_id is required"
                )
                return {"error": "invalid_input"}
        try:
            if context_run:
                return await _execute_context_generation(ctx, run)
            if copilot_run:
                return await _execute_copilot_run(ctx, run)
            assert isinstance(screenplay_id, int)
            result = await evaluate_screenplay(ctx, run) if evaluation_run else await analyze_screenplay(ctx, screenplay_id, run.agent_role)
        except Exception as exc:  # pragma: no cover - worker failure boundary
            return await _retry_or_fail(ctx, run_id, exc)
        async with session_scope() as session:
            run = await workflow_runs_crud.get(session, run_id)
            if run is not None and run.status != "cancelled":
                await workflow_runs_crud.update_status(session, run, "succeeded", result=result)
                return result
        return {"status": "cancelled"}


async def _retry_or_fail(ctx: dict, run_id: int, error: Exception) -> dict[str, object]:
    """Persist a bounded retry or terminal failure for a workflow run."""
    async with session_scope() as session:
        run = await workflow_runs_crud.get(session, run_id)
        if run is None:
            return {"error": "not_found"}
        if run.status == "cancelled":
            return {"status": "cancelled"}
        message = str(error)[:900]
        if run.attempt_count < run.max_attempts:
            await workflow_runs_crud.update_status(
                session,
                run,
                "queued",
                error=f"Attempt {run.attempt_count}/{run.max_attempts} failed: {message}",
            )
            should_retry = True
        else:
            await workflow_runs_crud.update_status(session, run, "failed", error=message)
            should_retry = False
    if should_retry:
        pool = await get_arq_pool()
        await pool.enqueue_job("execute_workflow", run_id)
        return {"status": "retrying", "attempt": run.attempt_count}
    return {"error": message, "status": "failed"}


async def _execute_context_generation(ctx: dict, run: WorkflowRun) -> dict[str, object]:
    """Generate a durable, review-only creative-context suggestion."""
    workflow_key = run.input.get("workflow")
    instruction = run.input.get("instruction")
    artifact_id = run.input.get("artifact_id")
    if not isinstance(workflow_key, str) or not isinstance(instruction, str):
        return await _fail_context_run(run.id or 0, "Invalid context workflow input")
    workflow = get_context_workflow(workflow_key)
    if workflow is None:
        return await _fail_context_run(run.id or 0, "Unknown context workflow")
    source_text = ""
    source_title = "project"
    if isinstance(artifact_id, int):
        async with session_scope() as session:
            artifact = await artifacts_crud.get(session, artifact_id)
            if artifact is None or artifact.project_id != run.project_id:
                return await _fail_context_run(run.id or 0, "Context artifact is unavailable")
            source_text = artifact.content[:12_000]
            source_title = artifact.title
    retrieved_context = await retrieve_context(run.project_id, instruction)
    prompt = (
        f"Workflow: {workflow.label}. Output kind: {workflow.output_kind}. "
        f"Source: {source_title}. Source material:\n{source_text}\n\n"
        f"Writer instruction: {instruction}"
    )
    try:
        suggestion = await generate_reply(
            prompt,
            f"context/{workflow.key}",
            workflow.output_kind,
            source_title,
            normalize_agent_role(run.agent_role),
            [],
            None,
            retrieved_context,
        )
    except Exception:  # pragma: no cover - provider/network dependent
        raise
    result: dict[str, object] = {
        "workflow": workflow.key,
        "output_kind": workflow.output_kind,
        "evaluator": workflow.evaluator,
        "suggestion": suggestion,
        "citations": [
            item["citation"]
            for item in retrieved_context
            if isinstance(item.get("citation"), dict)
        ],
        "source_artifact_id": artifact_id,
        "source_version": run.input.get("source_version"),
        "requires_review": True,
    }
    async with session_scope() as session:
        current = await workflow_runs_crud.get(session, run.id or 0)
        if current is None or current.status == "cancelled":
            return {"status": "cancelled"}
        await workflow_runs_crud.update_status(session, current, "succeeded", result=result)
    return result


async def _fail_context_run(run_id: int, error: str) -> dict[str, object]:
    """Record a context workflow failure without fabricating a result."""
    async with session_scope() as session:
        current = await workflow_runs_crud.get(session, run_id)
        if current is not None:
            await workflow_runs_crud.update_status(session, current, "failed", error=error)
    return {"error": error}


async def evaluate_screenplay(ctx: dict, run: WorkflowRun) -> dict[str, object]:
    """Compute and persist deterministic screenplay quality findings for one durable run."""
    screenplay_id = run.input.get("screenplay_id")
    if not isinstance(screenplay_id, int):
        raise ValueError("screenplay_id is required")
    async with session_scope() as session:
        scenes = await scenes_crud.list_for_screenplay(session, screenplay_id)
        empty_scenes: list[int] = []
        dialogue_count = 0
        character_count = 0
        for scene in scenes:
            blocks = await blocks_crud.list_for_scene(session, scene.id or 0)
            scene_text = scene.body.strip() or " ".join(block.text for block in blocks).strip()
            if not scene.heading.strip() or not scene_text:
                empty_scenes.append(scene.id or 0)
            dialogue_count += sum(block.element_type.value == "dialogue" for block in blocks)
            character_count += sum(block.element_type.value == "character" for block in blocks)
        scene_count = len(scenes)
        penalties = (len(empty_scenes) / scene_count if scene_count else 1.0) * 0.6
        if dialogue_count and not character_count:
            penalties += 0.2
        score = round(max(0.0, min(1.0, 1.0 - penalties)), 3)
        findings: dict[str, object] = {
            "scene_count": scene_count,
            "dialogue_count": dialogue_count,
            "character_count": character_count,
            "empty_scene_ids": empty_scenes,
        }
        evaluation = await evaluations_crud.create(
            session,
            EvaluationResult(
                project_id=run.project_id,
                target_kind="screenplay",
                target_id=screenplay_id,
                evaluator=str(run.input.get("evaluator", "deterministic_review")),
                score=score,
                summary=(
                    f"Reviewed {scene_count} scenes; "
                    f"{len(empty_scenes)} need content attention."
                ),
                findings=findings,
            ),
        )
    return {"evaluation_id": evaluation.id or 0, **findings, "score": score}


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
    except Exception:  # pragma: no cover - provider/network dependent
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
