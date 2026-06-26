"""Project model — the top-level container for a creator's work."""

from typing import TYPE_CHECKING

from sqlalchemy import JSON
from sqlmodel import Field, Relationship, SQLModel

from draftpilot.models.base import TimestampMixin
from draftpilot.models.enums import ScreeningType

if TYPE_CHECKING:
    from draftpilot.models.project_reference import ProjectReference
    from draftpilot.models.screenplay import Screenplay


class ProjectBase(SQLModel):
    """Shared project fields common to all project schemas."""

    title: str = Field(index=True, min_length=1, max_length=200)
    logline: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None)
    story_outline: str | None = Field(default=None)
    visual_style: str | None = Field(default=None, max_length=300)
    camera_type: str | None = Field(default=None, max_length=200)
    screening_type: ScreeningType | None = Field(default=None)
    artwork_url: str | None = Field(default=None, max_length=1000)
    artwork_path: str | None = Field(default=None, max_length=1000)
    genres: list[str] = Field(default_factory=list, sa_type=JSON)
    languages: list[str] = Field(default_factory=list, sa_type=JSON)


class Project(ProjectBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted project table — top-level container for a creator's work."""

    __tablename__ = "project"

    id: int | None = Field(default=None, primary_key=True)
    screenplays: list["Screenplay"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    references: list["ProjectReference"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ProjectCreate(ProjectBase):
    """Schema for creating a new project."""

    pass


class ProjectUpdate(SQLModel):
    """Schema for partially updating an existing project."""

    title: str | None = None
    logline: str | None = None
    description: str | None = None
    story_outline: str | None = None
    visual_style: str | None = None
    camera_type: str | None = None
    screening_type: ScreeningType | None = None
    artwork_url: str | None = None
    artwork_path: str | None = None
    genres: list[str] | None = None
    languages: list[str] | None = None


class ProjectRead(ProjectBase):
    """Schema for reading a project, including its identifier."""

    id: int
