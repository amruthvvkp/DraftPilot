"""Test the develop_story pipeline: every stage waits for the writer, and only approved work feeds the next."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from _async import run_async
from _temporal import temporal_worker
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.client import WorkflowExecutionStatus
from test_room_workflows import (  # noqa: F401 - project is a fixture
    SCENE,
    _all,
    _outline,
    _room,
    _scores,
    project,
)

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.models import register_model
from draftpilot.agents.workflows import RoomRunInput
from draftpilot.core import proposals
from draftpilot.models import (
    AgentProposal,
    Character,
    CharacterTimelineEvent,
    Project,
    Scene,
    StoryBeat,
    WorkflowRun,
)
from draftpilot.worker.activities import all_activities
from draftpilot.worker.workflows import all_workflows

PAYLOADS: dict[str, Any] = {
    "StorylineDraft": lambda _prompt, _count: {
        "title": "Big Fish",
        "logline": "A son chases the truth behind his dying father's tall tales.",
        "premise": "Can a story be truer than the facts?",
        "synopsis": "Will returns home as Edward dies, and finally hears the stories as his father meant them.",
        "theme": "Stories outlive us.",
        "tone": "Wistful, warm, fabulist.",
    },
    "Cast": lambda _prompt, _count: {
        "characters": [
            {"name": "Edward", "role": "protagonist", "summary": "A teller of tall tales.", "want": "To be a legend", "need": "To be known by his son", "objective": "Win back Will"},
            {"name": "Josephine", "role": "supporting", "summary": "Will's wife.", "want": "Peace", "need": "Truth"},
        ]
    },
    "CharacterTimeline": lambda _prompt, _count: {
        "moments": [
            {"story_time": "1937", "title": "Sees his death in the witch's eye", "objective": "Know his fate"},
            {"story_time": "today", "title": "Asks Will to tell the ending", "emotional_state": "At peace"},
        ]
    },
    "Outline": _outline,
    "Critique": _scores(9),
    "SceneDraft": lambda _prompt, _count: {"fountain": SCENE, "rationale": "True to the beat."},
    "Coverage": lambda _prompt, _count: {"logline": "L", "synopsis": "S", "premise": 8, "structure": 7, "character": 9, "dialogue": 7, "pacing": 6, "verdict": "consider"},
}


def test_develop_story_waits_for_the_writer_at_every_stage(project: AsyncSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: F811
    """Storyline → cast → timelines → outline → scenes → coverage, each gated on the writer's decisions."""
    ref = register_model(_room(PAYLOADS))
    decisions: list[tuple[str, str]] = []

    async def scenario() -> dict[str, Any]:
        """Run the pipeline while a scripted writer decides each proposal as it appears."""
        async with AsyncSession(project.bind, expire_on_commit=False) as session:
            run = WorkflowRun(project_id=1, kind="room_workflow", input={"workflow": "develop_story", "params": {}}, permission_mode="suggest")
            session.add(run)
            await session.commit()
            run_id = run.id or 0
        async with temporal_worker(all_workflows(), all_activities()) as (client, queue):

            async def get_client() -> object:
                """Let the proposals API signal the test server."""
                return client

            monkeypatch.setattr("draftpilot.core.temporal.get_client", get_client)
            room = RoomDeps(project_id=1, permission_mode="suggest", model_ref=ref, workflow_run_id=run_id, tools=False)
            params = {"idea": "A dying father's tall tales, and the son who wants the truth.", "cast_size": 2, "draft_beats": 2, "wait_hours": 1}
            handle = await client.start_workflow(
                "room:develop_story", RoomRunInput(workflow="develop_story", params=params, room=room), id=f"run-{run_id}-room", task_queue=queue
            )
            for _ in range(600):
                async with AsyncSession(project.bind, expire_on_commit=False) as session:
                    pending = [row for row in _all(session, AgentProposal) if row.status == "proposed"]
                    for row in pending:
                        name = str(row.operation.get("fields", {}).get("name", ""))
                        verdict = "rejected" if name == "Josephine" else "approved"
                        decisions.append((row.target_kind, verdict))
                        await (proposals.reject if verdict == "rejected" else proposals.approve)(session, 1, row.id or 0)
                description = await handle.describe()
                if description.status != WorkflowExecutionStatus.RUNNING:
                    break
                await asyncio.sleep(0.05)
            assert await handle.query("current_stage") == "finished"
            result: dict[str, Any] = await handle.result()
            return result

    result = run_async(scenario())
    stages = result["stages"]
    assert list(stages) == ["storyline", "characters", "timelines", "outline", "scenes"]
    assert stages["characters"] == {"proposed": 2, "approved": 1, "cast": ["Edward", "Josephine"]}
    assert stages["timelines"]["characters"] == ["Edward"]  # the rejected character got no timeline
    assert result["coverage"]["verdict"] == "consider"
    assert decisions[0] == ("storyline", "approved") and ("outline", "approved") in decisions
    story = run_async(project.get(Project, 1))
    assert story is not None
    edward = next(row for row in _all(project, Character) if row.name == "Edward")
    assert edward.want == "To be a legend" and not any(row.name == "Josephine" for row in _all(project, Character))
    assert [event.story_time for event in _all(project, CharacterTimelineEvent)] == ["1937", "today"]
    beats = sorted(_all(project, StoryBeat), key=lambda beat: beat.position)
    assert len(beats) == 3 and [beat.status for beat in beats] == ["drafted", "drafted", "planned"]
    assert all(len(beat.scene_ids) == 1 for beat in beats[:2])
    assert len(_all(project, Scene)) == 3  # the seeded scene plus two drafted ones
