"""Typed dependencies every room agent run receives.

They cross Temporal activity boundaries, so they hold only plain, serializable values: ids,
strings and the model ref, never sessions or model instances.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoomDeps:
    """Carry the writer's current focus, layered instructions, and the run's model into an agent run."""

    project_id: int
    page: str = ""
    artifact: str | None = None
    selection: str | None = None
    scene_id: int | None = None
    permission_mode: str = "chat_only"
    project_instruction: str = ""
    scene_instruction: str = ""
    writer_brief: str = ""
    story_brief: str = ""
    retrieved_context: list[dict[str, object]] = field(default_factory=list)
    # The model ref (``agents.models``); empty means the installation default.
    model_ref: str = ""
    # Whether the run may use DraftPilot tools at all (self-contained workflow steps may not).
    tools: bool = True
    workflow_run_id: int | None = None
