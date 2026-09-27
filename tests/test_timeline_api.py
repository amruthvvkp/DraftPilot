"""Test timeline proposal approval invalidation behavior."""

from unittest.mock import AsyncMock

from _async import run_async

from draftpilot.api.timeline import (
    approve_timeline_proposal,
    rollback_timeline_proposal,
)
from draftpilot.models import Scene, StoryArtifact, TimelineProposalRecord


class _Session:
    """Provide the session methods used by the approval endpoint."""

    def add(self, _value: object) -> None:
        """Accept a staged model change."""

    async def commit(self) -> None:
        """Commit the staged model changes."""

    async def refresh(self, _value: object) -> None:
        """Refresh the approved proposal fixture."""


def test_approve_timeline_marks_dependent_artifacts_stale(monkeypatch: object) -> None:
    """Invalidate downstream artifacts when a timeline reorder is approved."""
    proposal = TimelineProposalRecord(
        id=11,
        project_id=7,
        screenplay_id=3,
        original_scene_ids=[1, 2],
        proposed_scene_ids=[2, 1],
        timings=[],
    )
    scenes = [Scene(id=1, act_id=4, heading="INT. HOUSE - DAY", position=0), Scene(id=2, act_id=4, heading="EXT. ROAD - DAY", position=1)]
    timeline = StoryArtifact(id=20, project_id=7, kind="timeline", title="Timeline")
    dependent = StoryArtifact(id=21, project_id=7, kind="outline", title="Outline", depends_on=[20])
    get_proposal = AsyncMock(return_value=proposal)
    list_scenes = AsyncMock(return_value=scenes)
    list_artifacts = AsyncMock(return_value=[timeline, dependent])
    mark_stale = AsyncMock(return_value=[21])
    monkeypatch.setattr("draftpilot.api.timeline.proposals_crud.get", get_proposal)
    monkeypatch.setattr("draftpilot.api.timeline.scenes_crud.list_for_screenplay", list_scenes)
    monkeypatch.setattr("draftpilot.api.timeline.artifacts_crud.list_for_project", list_artifacts)
    monkeypatch.setattr("draftpilot.api.timeline.artifacts_crud.mark_dependents_stale", mark_stale)

    session = _Session()
    result = run_async(approve_timeline_proposal(7, 3, 11, session))

    assert result.status == "approved"
    mark_stale.assert_awaited_once_with(session, 7, [20])


def test_rollback_timeline_restores_order_and_marks_dependents_stale(monkeypatch: object) -> None:
    """Restore an approved reorder only when its proposed order is current."""
    proposal = TimelineProposalRecord(
        id=11,
        project_id=7,
        screenplay_id=3,
        original_scene_ids=[1, 2],
        proposed_scene_ids=[2, 1],
        timings=[],
        status="approved",
    )
    scenes = [
        Scene(id=2, act_id=4, heading="EXT. ROAD - DAY", position=0),
        Scene(id=1, act_id=4, heading="INT. HOUSE - DAY", position=1),
    ]
    timeline = StoryArtifact(id=20, project_id=7, kind="timeline", title="Timeline")
    get_proposal = AsyncMock(return_value=proposal)
    list_scenes = AsyncMock(return_value=scenes)
    list_artifacts = AsyncMock(return_value=[timeline])
    mark_stale = AsyncMock(return_value=[])
    monkeypatch.setattr("draftpilot.api.timeline.proposals_crud.get", get_proposal)
    monkeypatch.setattr("draftpilot.api.timeline.scenes_crud.list_for_screenplay", list_scenes)
    monkeypatch.setattr("draftpilot.api.timeline.artifacts_crud.list_for_project", list_artifacts)
    monkeypatch.setattr("draftpilot.api.timeline.artifacts_crud.mark_dependents_stale", mark_stale)

    session = _Session()
    result = run_async(rollback_timeline_proposal(7, 3, 11, session))

    assert result.status == "rolled_back"
    assert proposal.status == "rolled_back"
    assert [scene.position for scene in scenes] == [1, 0]
    assert all(scene.version == 2 for scene in scenes)
    mark_stale.assert_awaited_once_with(session, 7, [20])
