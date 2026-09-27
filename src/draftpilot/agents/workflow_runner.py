"""Start and finish persisted room workflow runs; the worker executes them on Temporal."""

from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.agents.context import load_room_context
from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.models import describe_model
from draftpilot.agents.workflows import ROOM_WORKFLOWS, RoomRunInput, validate_params
from draftpilot.core.db import session_scope
from draftpilot.crud import workflow_runs as runs_crud
from draftpilot.evals.online import online_checks
from draftpilot.models import WorkflowRun, WorkflowRunCreate

ROOM_WORKFLOW_KIND = "room_workflow"


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


async def prepare_room_run(run_id: int) -> tuple[str, RoomRunInput]:
    """Resolve a queued run's workflow, model and room context; return the workflow type and its input."""
    async with session_scope() as session:
        run = await runs_crud.get(session, run_id)
        if run is None:
            raise ValueError("Run not found")
        key = run.input.get("workflow")
        if not isinstance(key, str) or key not in ROOM_WORKFLOWS:
            raise ValueError("Unknown room workflow")
        params = run.input.get("params") if isinstance(run.input.get("params"), dict) else {}
        context = await load_room_context(session, run.project_id)
    profile_id = run.input.get("provider_profile_id")
    model_ref = await describe_model(profile_id if isinstance(profile_id, int) else None)
    room = RoomDeps(
        project_id=run.project_id,
        page="room",
        permission_mode="chat_only",
        project_instruction=context.project_instruction,
        writer_brief=context.writer_brief,
        story_brief=context.story_brief,
        model_ref=model_ref,
        workflow_run_id=run_id,
    )
    return ROOM_WORKFLOWS[key].type_name, RoomRunInput(workflow=key, params=params or {}, room=room)


def with_checks(result: dict[str, Any]) -> dict[str, Any]:
    """Add the online checks (the offline suites' deterministic evaluators) to a finished workflow's result."""
    return {**result, "checks": online_checks(str(result.get("workflow", "")), result)}
