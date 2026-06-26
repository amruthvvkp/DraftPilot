"""ProjectReference model — a typed creative reference cited by a project."""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from draftpilot.models.base import TimestampMixin
from draftpilot.models.enums import ReferenceKind

if TYPE_CHECKING:
    from draftpilot.models.project import Project


class ProjectReferenceBase(SQLModel):
    """Shared project-reference fields common to all schemas."""

    kind: ReferenceKind = Field(default=ReferenceKind.OTHER)
    label: str = Field(min_length=1, max_length=300)
    url: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=1000)


class ProjectReference(ProjectReferenceBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted project-reference table — a typed creative reference."""

    __tablename__ = "project_reference"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)

    project: "Project" = Relationship(back_populates="references")


class ProjectReferenceCreate(ProjectReferenceBase):
    """Schema for creating a new project reference."""

    project_id: int


class ProjectReferenceUpdate(SQLModel):
    """Schema for partially updating an existing project reference."""

    kind: ReferenceKind | None = None
    label: str | None = None
    url: str | None = None
    note: str | None = None


class ProjectReferenceRead(ProjectReferenceBase):
    """Schema for reading a project reference, including its identifiers."""

    id: int
    project_id: int
