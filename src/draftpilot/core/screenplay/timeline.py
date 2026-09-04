"""Pure timeline proposal calculations for reversible screenplay reordering."""

from collections.abc import Mapping, Sequence

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


def estimate_scene_duration_seconds(body: str, block_texts: list[str] | None = None) -> int:
    """Calculate conservative estimated scene duration in seconds."""
    text = body.strip() or (" ".join(block_texts).strip() if block_texts else "")
    words = len(text.split()) if text else 0
    return max(30, round(words / 2))


def target_runtime_seconds_for_format(format_name: str | None) -> int:
    """Return the target runtime budget in seconds for a screenplay format."""
    normalized = (format_name or "feature").strip().casefold()
    if normalized == "short":
        return 900
    if normalized in {"pilot", "series_pilot", "tv"}:
        return 3600
    return 6600


def calculate_scene_timings(
    scenes: Sequence[object],
    blocks: Mapping[int, Sequence[object]] | None = None,
) -> tuple[list[SceneTiming], int]:
    """Compute ordered scene timings and total runtime seconds."""
    offset = 0
    timings: list[SceneTiming] = []
    for position, scene in enumerate(scenes):
        scene_id = getattr(scene, "id", None) or 0
        scene_body = getattr(scene, "body", "") or ""
        scene_blocks = blocks.get(scene_id, []) if blocks else []
        block_texts = [
            getattr(block, "text", str(block)) for block in scene_blocks if getattr(block, "text", str(block))
        ]
        duration = estimate_scene_duration_seconds(scene_body, block_texts)
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
    return timings, offset

