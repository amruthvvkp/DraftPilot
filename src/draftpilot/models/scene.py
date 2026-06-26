"""Scene model — an ordered unit of an act."""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from draftpilot.models.base import TimestampMixin

if TYPE_CHECKING:
    from draftpilot.models.act import Act
    from draftpilot.models.block import Block
    from draftpilot.models.scene_revision import SceneRevision


class SceneBase(SQLModel):
    """Shared scene fields common to all scene schemas."""

    heading: str = Field(max_length=300)  # e.g. "INT. COFFEE SHOP - DAY"
    position: int = Field(default=0, index=True)
    body: str = Field(default="")  # rendered cache; the ground truth is ``blocks``


class Scene(SceneBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted scene table — an ordered unit of an act."""

    __tablename__ = "scene"

    id: int | None = Field(default=None, primary_key=True)
    act_id: int = Field(foreign_key="act.id", index=True)

    act: "Act" = Relationship(back_populates="scenes")
    blocks: list["Block"] = Relationship(
        back_populates="scene",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "Block.position",
        },
    )
    revisions: list["SceneRevision"] = Relationship(
        back_populates="scene",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "SceneRevision.rev_number",
        },
    )


class SceneCreate(SceneBase):
    """Schema for creating a new scene."""

    act_id: int


class SceneUpdate(SQLModel):
    """Schema for partially updating an existing scene."""

    heading: str | None = None
    position: int | None = None
    body: str | None = None


class SceneRead(SceneBase):
    """Schema for reading a scene, including its identifiers."""

    id: int
    act_id: int
