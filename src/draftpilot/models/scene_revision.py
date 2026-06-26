"""SceneRevision model — an append-only snapshot of a scene's content."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime
from sqlmodel import Field, Relationship, SQLModel

from draftpilot.models.base import _utcnow

if TYPE_CHECKING:
    from draftpilot.models.scene import Scene


class SceneRevisionBase(SQLModel):
    """Shared scene-revision fields common to all schemas."""

    rev_number: int = Field(default=1, index=True)
    message: str | None = Field(default=None, max_length=300)


class SceneRevision(SceneRevisionBase, table=True):  # type: ignore[call-arg]
    """Persisted scene-revision table — an append-only scene snapshot."""

    __tablename__ = "scene_revision"

    id: int | None = Field(default=None, primary_key=True)
    scene_id: int = Field(foreign_key="scene.id", index=True)
    # Serialized ``SceneDoc`` (heading + ordered blocks) captured at snapshot time.
    snapshot: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        nullable=False,
    )

    scene: "Scene" = Relationship(back_populates="revisions")


class SceneRevisionRead(SceneRevisionBase):
    """Schema for reading a scene revision, including its identifiers."""

    id: int
    scene_id: int
    created_at: datetime
