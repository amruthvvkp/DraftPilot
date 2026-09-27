"""Run a persisted room workflow: resolve the model, stream progress into the run, honour cancellation."""

from typing import Any

import logfire
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.agents.context import load_room_context
from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.workflows import (
    ROOM_WORKFLOWS,
    WorkflowDeps,
    run_room_workflow,
    validate_params,
)
from draftpilot.core import events
from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.db import session_scope
from draftpilot.core.providers import build_chat_model, settings_from_profile
from draftpilot.core.usefulness import score_traces, traces_for_run
from draftpilot.crud import provider_profiles as profiles_crud
from draftpilot.crud import workflow_runs as runs_crud
from draftpilot.evals.online import online_checks
from draftpilot.models import WorkflowRun, WorkflowRunCreate

ROOM_WORKFLOW_KIND = "room_workflow"


class WorkflowCancelled(Exception):
    """Raised between steps when the writer cancels a running workflow."""


async def create_room_workflow_run(
    session: AsyncSession,
    project_id: int,
    workflow: str,
    params: dict[str, Any],
    provider_profile_id: int | None = None,
) -> WorkflowRun:
    """Validate a room workflow's parameters and persist its queued run.

    Raises ``KeyError`` for an unknown workflow and ``ValidationError`` for bad parameters. Runs are
    ``suggest``-mode (they end in proposals) and single-attempt (a retry would re-bill every step).
    """
    validated = validate_params(workflow, params)
    return await runs_crud.create(
        session,
        WorkflowRunCreate(
            project_id=project_id,
            kind=ROOM_WORKFLOW_KIND,
            input={"workflow": workflow, "params": validated.model_dump(mode="json"), "provider_profile_id": provider_profile_id},
            agent_role="showrunner",
            permission_mode="suggest",
            max_attempts=1,
        ),
    )


async def _llm_settings(provider_profile_id: object) -> LLMSettings:
    """Return the run's chosen provider profile, or the installation default."""
    if not isinstance(provider_profile_id, int):
        return settings.llm
    async with session_scope() as session:
        profile = await profiles_crud.get(session, provider_profile_id)
    if profile is None:
        raise ValueError("Provider profile not found")
    return settings_from_profile(profile)


async def execute_room_workflow(run: WorkflowRun) -> dict[str, Any]:
    """Execute one room workflow run to its gate, persisting the trail after every consultation."""
    key = run.input.get("workflow")
    if not isinstance(key, str) or key not in ROOM_WORKFLOWS:
        raise ValueError("Unknown room workflow")
    params = run.input.get("params") if isinstance(run.input.get("params"), dict) else {}
    config = await _llm_settings(run.input.get("provider_profile_id"))
    if not config.enabled:
        raise RuntimeError("LLM provider is disabled")
    model, model_name = await build_chat_model(config)
    run_id = run.id or 0
    async with session_scope() as session:
        context = await load_room_context(session, run.project_id)

    async def progress(trail: list[dict[str, Any]]) -> None:
        """Persist the trail so far, and stop if the writer cancelled."""
        async with session_scope() as session:
            current = await runs_crud.get(session, run_id)
            if current is None or current.status == "cancelled":
                raise WorkflowCancelled
            current.result = {"workflow": key, "stage": "running", "trail": trail}
            session.add(current)
            await session.commit()
        await events.publish(
            run.project_id, "workflow.progress", {"run_id": run_id, "steps": len(trail), "last": trail[-1]["step"]}
        )

    deps = WorkflowDeps(
        model=model,
        provider=config.provider,
        model_name=model_name,
        room=RoomDeps(
            project_id=run.project_id,
            page="room",
            permission_mode="chat_only",
            project_instruction=context.project_instruction,
            writer_brief=context.writer_brief,
            story_brief=context.story_brief,
        ),
        run_id=run_id,
        progress=progress,
    )
    with logfire.span("room workflow {workflow}", workflow=key, run_id=run_id, project_id=run.project_id):
        result = await run_room_workflow(key, params or {}, deps)
    result["checks"] = online_checks(key, result)
    async with session_scope() as session:
        traces = await traces_for_run(session, run_id)
    for name, value in result["checks"].items():
        await score_traces(traces, f"check_{name}", value)
    return result
