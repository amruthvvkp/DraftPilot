"""Act model — an ordered division of a screenplay grouping scenes."""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from draftpilot.models.base import TimestampMixin

if TYPE_CHECKING:
    from draftpilot.models.scene import Scene
    from draftpilot.models.screenplay import Screenplay


class ActBase(SQLModel):
    """Shared act fields common to all act schemas."""

    title: str | None = Field(default=None, max_length=200)  # e.g. "Act One"
    position: int = Field(default=0, index=True)


class Act(ActBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted act table — an ordered division of a screenplay."""

    __tablename__ = "act"

    id: int | None = Field(default=None, primary_key=True)
    screenplay_id: int = Field(foreign_key="screenplay.id", index=True)

    screenplay: "Screenplay" = Relationship(back_populates="acts")
    scenes: list["Scene"] = Relationship(
        back_populates="act",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "Scene.position",
        },
    )


class ActCreate(ActBase):
    """Schema for creating a new act."""

    screenplay_id: int


class ActUpdate(SQLModel):
    """Schema for partially updating an existing act."""

    title: str | None = None
    position: int | None = None


class ActRead(ActBase):
    """Schema for reading an act, including its identifiers."""

    id: int
    screenplay_id: int
