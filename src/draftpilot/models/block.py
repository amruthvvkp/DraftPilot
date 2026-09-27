"""Block model — a single typed screenplay element within a scene."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON
from sqlmodel import Field, Relationship, SQLModel

from draftpilot.models.base import TimestampMixin
from draftpilot.models.enums import BlockType

if TYPE_CHECKING:
    from draftpilot.models.dialogue_translation import DialogueTranslation
    from draftpilot.models.scene import Scene


class BlockBase(SQLModel):
    """Shared block fields common to all block schemas."""

    position: int = Field(default=0, index=True)
    element_type: BlockType = Field(default=BlockType.ACTION)
    text: str = Field(default="")  # may carry Fountain-style **bold**/*italic*/_underline_
    character_extension: str | None = Field(default=None, max_length=50)  # e.g. "(V.O.)"
    is_dual: bool = Field(default=False)
    dual_group: int | None = Field(default=None)
    translation: str | None = Field(default=None)
    translation_lang: str | None = Field(default=None, max_length=20)


class Block(BlockBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted block table — a single typed screenplay element."""

    __tablename__ = "block"

    id: int | None = Field(default=None, primary_key=True)
    scene_id: int = Field(foreign_key="scene.id", index=True)
    # Non-standard inline marks (e.g. font colour) the Fountain/FDX formats cannot carry.
    marks: dict[str, Any] | None = Field(default=None, sa_type=JSON)
    # Who last authored the text: "human", "import", or "proposal:<id>" (an approved agent change).
    origin: str = Field(default="human", max_length=120)

    scene: "Scene" = Relationship(back_populates="blocks")
    translations: list["DialogueTranslation"] = Relationship(
        back_populates="block",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "DialogueTranslation.language"},
    )


class BlockCreate(BlockBase):
    """Schema for creating a new block."""

    scene_id: int
    marks: dict[str, Any] | None = None


class BlockUpdate(SQLModel):
    """Schema for partially updating an existing block."""

    position: int | None = None
    element_type: BlockType | None = None
    text: str | None = None
    character_extension: str | None = None
    is_dual: bool | None = None
    dual_group: int | None = None
    translation: str | None = None
    translation_lang: str | None = None
    marks: dict[str, Any] | None = None


class BlockRead(BlockBase):
    """Schema for reading a block, including its identifiers."""

    id: int
    scene_id: int
    marks: dict[str, Any] | None = None
    origin: str = "human"
