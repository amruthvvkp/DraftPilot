"""Project model — the top-level container for a creator's work."""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from draftpilot.models.base import TimestampMixin

if TYPE_CHECKING:
    from draftpilot.models.screenplay import Screenplay


class ProjectBase(SQLModel):
    """Shared project fields common to all project schemas."""

    title: str = Field(index=True, min_length=1, max_length=200)
    logline: str | None = Field(default=None, max_length=500)
    genre: str | None = Field(default=None, max_length=100)


class Project(ProjectBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted project table — top-level container for a creator's work."""

    __tablename__ = "project"

    id: int | None = Field(default=None, primary_key=True)
    screenplays: list["Screenplay"] = Relationship(
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
    genre: str | None = None


class ProjectRead(ProjectBase):
    """Schema for reading a project, including its identifier."""

    id: int
