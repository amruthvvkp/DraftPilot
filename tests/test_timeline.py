"""Test deterministic screenplay timeline proposals."""

import pytest

from draftpilot.core.screenplay.timeline import propose_reorder


def test_reorder_recalculates_offsets_without_applying_changes() -> None:
    """Calculate offsets in proposed order and flag dependent artifacts stale."""
    proposal = propose_reorder([1, 2, 3], [3, 1, 2], {1: 90, 2: 60, 3: 45})
    assert proposal.scene_ids == [3, 1, 2]
    assert [(timing.start_seconds, timing.end_seconds) for timing in proposal.timings] == [
        (0, 45),
        (45, 135),
        (135, 195),
    ]
    assert proposal.total_runtime_seconds == 195
    assert proposal.dependent_artifacts_stale is True


@pytest.mark.parametrize(
    ("current", "proposed"),
    [([1, 2], [1]), ([1, 2], [1, 3]), ([1, 2], [2, 1, 1])],
)
def test_reorder_rejects_incomplete_or_duplicate_scene_sets(
    current: list[int], proposed: list[int]
) -> None:
    """Reject proposals that could silently discard screenplay scenes."""
    with pytest.raises(ValueError):
        propose_reorder(current, proposed, {1: 60, 2: 60, 3: 60})


def test_estimate_scene_duration_and_target_runtime() -> None:
    """Calculate conservative scene durations and format runtime targets."""
    from draftpilot.core.screenplay.timeline import (
        estimate_scene_duration_seconds,
        target_runtime_seconds_for_format,
    )

    assert estimate_scene_duration_seconds("") == 30
    assert estimate_scene_duration_seconds("word " * 100) == 50
    assert estimate_scene_duration_seconds("", ["word " * 60]) == 30
    assert target_runtime_seconds_for_format("feature") == 6600
    assert target_runtime_seconds_for_format("pilot") == 3600
    assert target_runtime_seconds_for_format("short") == 900
    assert target_runtime_seconds_for_format(None) == 6600


def test_calculate_scene_timings_computes_offsets_and_total() -> None:
    """Compute cumulative start and end offsets across ordered scenes."""
    from draftpilot.core.screenplay.timeline import calculate_scene_timings

    class _MockScene:
        """Stand in for scene models in timing tests."""

        def __init__(self, scene_id: int, body: str) -> None:
            """Initialize mock scene identifiers."""
            self.id = scene_id
            self.body = body

    scenes = [_MockScene(1, "word " * 80), _MockScene(2, "")]
    timings, total = calculate_scene_timings(scenes)
    assert len(timings) == 2
    assert timings[0].estimated_duration_seconds == 40
    assert timings[0].start_seconds == 0
    assert timings[0].end_seconds == 40
    assert timings[1].estimated_duration_seconds == 30
    assert timings[1].start_seconds == 40
    assert timings[1].end_seconds == 70
    assert total == 70

