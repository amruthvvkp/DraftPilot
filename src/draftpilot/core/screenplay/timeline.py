"""Pure timeline proposal calculations for reversible screenplay reordering."""

from pydantic import BaseModel, Field


class SceneTiming(BaseModel):
    """Describe one scene's proposed order and cumulative runtime."""

    scene_id: int
    position: int = Field(ge=0)
    estimated_duration_seconds: int = Field(ge=1)
    start_seconds: int = Field(ge=0)
    end_seconds: int = Field(ge=1)


class TimelineProposal(BaseModel):
    """Describe a pending reorder without applying it to screenplay data."""

    scene_ids: list[int]
    timings: list[SceneTiming]
    total_runtime_seconds: int = Field(ge=0)
    dependent_artifacts_stale: bool = True


def propose_reorder(
    current_scene_ids: list[int],
    proposed_scene_ids: list[int],
    durations: dict[int, int],
) -> TimelineProposal:
    """Build a validated reorder proposal with cumulative scene offsets."""
    if len(current_scene_ids) != len(proposed_scene_ids):
        raise ValueError("A reorder must contain every screenplay scene exactly once")
    if set(current_scene_ids) != set(proposed_scene_ids):
        raise ValueError("A reorder cannot add or remove screenplay scenes")
    if any(scene_id not in durations or durations[scene_id] < 1 for scene_id in proposed_scene_ids):
        raise ValueError("Every scene needs a positive estimated duration")
    offset = 0
    timings: list[SceneTiming] = []
    for position, scene_id in enumerate(proposed_scene_ids):
        duration = durations[scene_id]
        timings.append(
            SceneTiming(
                scene_id=scene_id,
                position=position,
                estimated_duration_seconds=duration,
                start_seconds=offset,
                end_seconds=offset + duration,
            )
        )
        offset += duration
    return TimelineProposal(
        scene_ids=proposed_scene_ids,
        timings=timings,
        total_runtime_seconds=offset,
    )
