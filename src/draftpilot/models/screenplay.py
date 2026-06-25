"""Screenplay model — a draft belonging to a project."""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from draftpilot.models.base import TimestampMixin

if TYPE_CHECKING:
    from draftpilot.models.project import Project
    from draftpilot.models.scene import Scene


class ScreenplayBase(SQLModel):
    """Shared screenplay fields common to all screenplay schemas."""

    title: str = Field(index=True, min_length=1, max_length=200)
    format: str = Field(default="feature", max_length=50)  # feature, short, pilot...
    status: str = Field(default="draft", max_length=50)  # draft, revision, final...


class Screenplay(ScreenplayBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted screenplay table — a draft belonging to a project."""

    __tablename__ = "screenplay"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)

    project: "Project" = Relationship(back_populates="screenplays")
    scenes: list["Scene"] = Relationship(
        back_populates="screenplay",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "Scene.position",
        },
    )


class ScreenplayCreate(ScreenplayBase):
    """Schema for creating a new screenplay."""

    project_id: int


class ScreenplayUpdate(SQLModel):
    """Schema for partially updating an existing screenplay."""

    title: str | None = None
    format: str | None = None
    status: str | None = None


class ScreenplayRead(ScreenplayBase):
    """Schema for reading a screenplay, including its identifiers."""

    id: int
    project_id: int
