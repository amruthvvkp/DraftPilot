"""Typed dependencies every room agent run receives."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoomDeps:
    """Carry the writer's current focus and layered instructions into an agent run."""

    project_id: int
    page: str = ""
    artifact: str | None = None
    selection: str | None = None
    scene_id: int | None = None
    permission_mode: str = "chat_only"
    project_instruction: str = ""
    scene_instruction: str = ""
    retrieved_context: list[dict[str, object]] = field(default_factory=list)
