"""Nested Pydantic ground-truth schema for a screenplay document.

``ScreenplayDoc`` is the canonical in-memory representation that import/export
adapters translate to and from, and that scene revisions serialize.
"""

from typing import Any

from pydantic import BaseModel, Field

from draftpilot.models.enums import BlockType


class BlockDoc(BaseModel):
    """Represent a single typed screenplay element within a scene."""

    element_type: BlockType = BlockType.ACTION
    text: str = ""
    character_extension: str | None = None
    is_dual: bool = False
    dual_group: int | None = None
    translation: str | None = None
    translation_lang: str | None = None
    marks: dict[str, Any] | None = None


class SceneDoc(BaseModel):
    """Represent a scene: a heading plus its ordered blocks."""

    heading: str = ""
    blocks: list[BlockDoc] = Field(default_factory=list)


class ActDoc(BaseModel):
    """Represent an act: an optional title plus its ordered scenes."""

    title: str | None = None
    scenes: list[SceneDoc] = Field(default_factory=list)


class ScreenplayDoc(BaseModel):
    """Represent a full screenplay: title-page metadata plus ordered acts."""

    title_page: dict[str, str] = Field(default_factory=dict)
    acts: list[ActDoc] = Field(default_factory=list)
