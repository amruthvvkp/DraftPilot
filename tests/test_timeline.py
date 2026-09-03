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
