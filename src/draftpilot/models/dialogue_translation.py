"""Dialogue translation model for source-preserving multilingual screenplay blocks."""

from typing import TYPE_CHECKING

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from draftpilot.models.base import TimestampMixin

if TYPE_CHECKING:
    from draftpilot.models.block import Block


class DialogueTranslationBase(SQLModel):
    """Shared fields for a linked dialogue translation."""

    language: str = Field(min_length=2, max_length=50)
    text: str = Field(default="")
    source_version: int = Field(default=1, ge=1)
    status: str = Field(default="draft", max_length=30)


class DialogueTranslation(DialogueTranslationBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persist a translation without changing the source dialogue block."""

    __tablename__ = "dialogue_translation"
    __table_args__ = (UniqueConstraint("block_id", "language", name="uq_dialogue_translation_block_language"),)

    id: int | None = Field(default=None, primary_key=True)
    block_id: int = Field(foreign_key="block.id", index=True)
    block: "Block" = Relationship(back_populates="translations")


class DialogueTranslationCreate(DialogueTranslationBase):
    """Describe a new linked dialogue translation."""

    block_id: int


class DialogueTranslationRead(DialogueTranslationBase):
    """Return a linked dialogue translation with its identifier."""

    id: int
    block_id: int
