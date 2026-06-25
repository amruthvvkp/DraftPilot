"""Scene model — an ordered unit of a screenplay."""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from draftpilot.models.base import TimestampMixin

if TYPE_CHECKING:
    from draftpilot.models.screenplay import Screenplay


class SceneBase(SQLModel):
    """Shared scene fields common to all scene schemas."""

    heading: str = Field(max_length=300)  # e.g. "INT. COFFEE SHOP - DAY"
    position: int = Field(default=0, index=True)
    body: str = Field(default="")


class Scene(SceneBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted scene table — an ordered unit of a screenplay."""

    __tablename__ = "scene"

    id: int | None = Field(default=None, primary_key=True)
    screenplay_id: int = Field(foreign_key="screenplay.id", index=True)

    screenplay: "Screenplay" = Relationship(back_populates="scenes")


class SceneCreate(SceneBase):
    """Schema for creating a new scene."""

    screenplay_id: int


class SceneUpdate(SQLModel):
    """Schema for partially updating an existing scene."""

    heading: str | None = None
    position: int | None = None
    body: str | None = None


class SceneRead(SceneBase):
    """Schema for reading a scene, including its identifiers."""

    id: int
    screenplay_id: int
