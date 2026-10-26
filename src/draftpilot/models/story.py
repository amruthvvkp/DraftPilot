"""Typed story-development entities: characters, their timelines and relationships, locations, beats.

These are the writer-owned canonical records behind the guided flow (storyline → characters →
outline → script). The Twin Keeper also derives characters and locations from the draft
(``source="twin"``); a writer edit sets ``writer_edited`` so later derivations never overwrite it.
"""

from typing import Any

from sqlalchemy import JSON, Column, ForeignKey, Integer
from sqlmodel import Field, SQLModel

from draftpilot.models.base import TimestampMixin

ENTITY_SOURCES = ("writer", "twin", "agent", "import")


def _project_fk() -> Any:
    """Return a project foreign key column that cascades on project delete."""
    return Field(sa_column=Column(Integer, ForeignKey("project.id", ondelete="CASCADE"), index=True, nullable=False))


class CharacterBase(SQLModel):
    """Writer-editable character profile: who they are, what drives them, how they change."""

    name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="supporting", max_length=40)  # protagonist, antagonist, supporting, minor
    summary: str = Field(default="", max_length=1000)
    bio: str = Field(default="")
    want: str = Field(default="", max_length=2000)  # conscious, external goal
    need: str = Field(default="", max_length=2000)  # unconscious, internal need
    motive: str = Field(default="", max_length=2000)
    objective: str = Field(default="", max_length=2000)
    flaw: str = Field(default="", max_length=2000)
    arc_summary: str = Field(default="", max_length=4000)
    voice: str = Field(default="", max_length=2000)
    notes: str = Field(default="")
    aliases: list[str] = Field(default_factory=list, sa_type=JSON)
    tags: list[str] = Field(default_factory=list, sa_type=JSON)
    position: int = Field(default=0)


class Character(CharacterBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted character with derived screenplay statistics."""

    __tablename__ = "character"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = _project_fk()
    cue: str | None = Field(default=None, max_length=200, index=True)  # normalised dialogue cue
    dialogue_lines: int = Field(default=0)
    scene_ids: list[int] = Field(default_factory=list, sa_type=JSON)
    source: str = Field(default="writer", max_length=20)
    writer_edited: bool = Field(default=False)
    version: int = Field(default=1, ge=1)


class CharacterCreate(CharacterBase):
    """Fields a writer or agent supplies to create a character."""

    cue: str | None = None


class CharacterUpdate(SQLModel):
    """Partial character update."""

    name: str | None = None
    role: str | None = None
    summary: str | None = None
    bio: str | None = None
    want: str | None = None
    need: str | None = None
    motive: str | None = None
    objective: str | None = None
    flaw: str | None = None
    arc_summary: str | None = None
    voice: str | None = None
    notes: str | None = None
    aliases: list[str] | None = None
    tags: list[str] | None = None
    position: int | None = None
    cue: str | None = None


class CharacterRead(CharacterBase):
    """Character with identity, derived stats and version."""

    id: int
    project_id: int
    cue: str | None
    dialogue_lines: int
    scene_ids: list[int]
    source: str
    writer_edited: bool
    version: int


class CharacterRelationshipBase(SQLModel):
    """A directed relationship between two characters."""

    source_character_id: int
    target_character_id: int
    relation: str = Field(min_length=1, max_length=100)  # e.g. "father of", "rival"
    description: str = Field(default="", max_length=2000)


class CharacterRelationship(CharacterRelationshipBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted character relationship."""

    __tablename__ = "character_relationship"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = _project_fk()
    source_character_id: int = Field(
        sa_column=Column(Integer, ForeignKey("character.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    target_character_id: int = Field(
        sa_column=Column(Integer, ForeignKey("character.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    version: int = Field(default=1, ge=1)


class CharacterRelationshipCreate(CharacterRelationshipBase):
    """Fields to create a relationship."""


class CharacterRelationshipUpdate(SQLModel):
    """Partial relationship update."""

    relation: str | None = None
    description: str | None = None


class CharacterRelationshipRead(CharacterRelationshipBase):
    """Relationship with identity and version."""

    id: int
    project_id: int
    version: int


class CharacterTimelineEventBase(SQLModel):
    """One moment in a character's personal timeline, optionally tied to a scene or beat."""

    character_id: int
    position: int = Field(default=0)
    story_time: str = Field(default="", max_length=100)  # e.g. "1973", "Day 3, night"
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=4000)
    objective: str = Field(default="", max_length=2000)  # what they want in this moment
    emotional_state: str = Field(default="", max_length=300)
    scene_id: int | None = None
    beat_id: int | None = None


class CharacterTimelineEvent(CharacterTimelineEventBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted character timeline event."""

    __tablename__ = "character_timeline_event"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = _project_fk()
    character_id: int = Field(
        sa_column=Column(Integer, ForeignKey("character.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    scene_id: int | None = Field(
        default=None, sa_column=Column(Integer, ForeignKey("scene.id", ondelete="SET NULL"), nullable=True)
    )
    beat_id: int | None = Field(
        default=None, sa_column=Column(Integer, ForeignKey("story_beat.id", ondelete="SET NULL"), nullable=True)
    )
    version: int = Field(default=1, ge=1)


class CharacterTimelineEventCreate(CharacterTimelineEventBase):
    """Fields to create a timeline event."""


class CharacterTimelineEventUpdate(SQLModel):
    """Partial timeline event update."""

    position: int | None = None
    story_time: str | None = None
    title: str | None = None
    description: str | None = None
    objective: str | None = None
    emotional_state: str | None = None
    scene_id: int | None = None
    beat_id: int | None = None


class CharacterTimelineEventRead(CharacterTimelineEventBase):
    """Timeline event with identity and version."""

    id: int
    project_id: int
    version: int


class LocationBase(SQLModel):
    """Writer-editable location: where scenes happen and how it should feel."""

    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=4000)
    visual_notes: str = Field(default="", max_length=4000)
    notes: str = Field(default="")
    position: int = Field(default=0)


class Location(LocationBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted location with derived heading statistics."""

    __tablename__ = "location"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = _project_fk()
    heading_location: str | None = Field(default=None, max_length=300, index=True)
    int_ext: list[str] = Field(default_factory=list, sa_type=JSON)
    times: list[str] = Field(default_factory=list, sa_type=JSON)
    scene_ids: list[int] = Field(default_factory=list, sa_type=JSON)
    source: str = Field(default="writer", max_length=20)
    writer_edited: bool = Field(default=False)
    version: int = Field(default=1, ge=1)


class LocationCreate(LocationBase):
    """Fields to create a location."""

    heading_location: str | None = None


class LocationUpdate(SQLModel):
    """Partial location update."""

    name: str | None = None
    description: str | None = None
    visual_notes: str | None = None
    notes: str | None = None
    position: int | None = None
    heading_location: str | None = None


class LocationRead(LocationBase):
    """Location with identity, derived stats and version."""

    id: int
    project_id: int
    heading_location: str | None
    int_ext: list[str]
    times: list[str]
    scene_ids: list[int]
    source: str
    writer_edited: bool
    version: int


class StoryBeatBase(SQLModel):
    """One outline beat, placed in an act and linked to the scenes that dramatise it."""

    act_id: int | None = None
    position: int = Field(default=0)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(default="", max_length=4000)
    beat_type: str = Field(default="beat", max_length=60)  # e.g. inciting_incident, midpoint, climax
    status: str = Field(default="planned", max_length=30)  # planned, drafted, cut
    scene_ids: list[int] = Field(default_factory=list, sa_type=JSON)
    character_ids: list[int] = Field(default_factory=list, sa_type=JSON)


class StoryBeat(StoryBeatBase, TimestampMixin, table=True):  # type: ignore[call-arg]
    """Persisted outline beat."""

    __tablename__ = "story_beat"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = _project_fk()
    act_id: int | None = Field(
        default=None, sa_column=Column(Integer, ForeignKey("act.id", ondelete="SET NULL"), nullable=True, index=True)
    )
    source: str = Field(default="writer", max_length=20)
    version: int = Field(default=1, ge=1)


class StoryBeatCreate(StoryBeatBase):
    """Fields to create a beat."""


class StoryBeatUpdate(SQLModel):
    """Partial beat update."""

    act_id: int | None = None
    position: int | None = None
    title: str | None = None
    summary: str | None = None
    beat_type: str | None = None
    status: str | None = None
    scene_ids: list[int] | None = None
    character_ids: list[int] | None = None


class StoryBeatRead(StoryBeatBase):
    """Beat with identity and version."""

    id: int
    project_id: int
    source: str
    version: int
