"""One service for every typed story entity, shared by REST, MCP, proposals and the room.

Each kind (character, relationship, timeline event, location, beat) is described once in
``KINDS``; create/update/delete validate project scope and cross references, enforce optimistic
concurrency, publish a live-sync event and refresh the RAG index.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import events, indexing
from draftpilot.core.errors import Invalid, NotFound, check_version
from draftpilot.models import (
    Act,
    Character,
    CharacterCreate,
    CharacterRead,
    CharacterRelationship,
    CharacterRelationshipCreate,
    CharacterRelationshipRead,
    CharacterRelationshipUpdate,
    CharacterTimelineEvent,
    CharacterTimelineEventCreate,
    CharacterTimelineEventRead,
    CharacterTimelineEventUpdate,
    CharacterUpdate,
    Location,
    LocationCreate,
    LocationRead,
    LocationUpdate,
    Scene,
    Screenplay,
    StoryBeat,
    StoryBeatCreate,
    StoryBeatRead,
    StoryBeatUpdate,
)


def _lines(*pairs: tuple[str, object]) -> str:
    """Join labelled non-empty values into indexable text."""
    return "\n".join(f"{label}: {value}" for label, value in pairs if value)


def _character_text(row: Any) -> str:
    """Render a character profile as retrieval text."""
    return _lines(
        ("Character", row.name),
        ("Role", row.role),
        ("Summary", row.summary),
        ("Bio", row.bio),
        ("Want", row.want),
        ("Need", row.need),
        ("Motive", row.motive),
        ("Objective", row.objective),
        ("Flaw", row.flaw),
        ("Arc", row.arc_summary),
        ("Voice", row.voice),
        ("Notes", row.notes),
    )


def _location_text(row: Any) -> str:
    """Render a location as retrieval text."""
    return _lines(("Location", row.name), ("Description", row.description), ("Look", row.visual_notes), ("Notes", row.notes))


def _beat_text(row: Any) -> str:
    """Render an outline beat as retrieval text."""
    return _lines(("Beat", row.title), ("Type", row.beat_type), ("Summary", row.summary))


def _event_text(row: Any) -> str:
    """Render a character timeline event as retrieval text."""
    return _lines(
        ("Timeline event", row.title),
        ("When", row.story_time),
        ("What happens", row.description),
        ("Objective", row.objective),
        ("Emotional state", row.emotional_state),
    )


def _relationship_text(row: Any) -> str:
    """Render a relationship as retrieval text."""
    return _lines(("Relationship", row.relation), ("Description", row.description))


@dataclass(frozen=True)
class EntityKind:
    """Describe one typed story entity for the shared service."""

    name: str
    label: str
    model: type[SQLModel]
    create: type[SQLModel]
    update: type[SQLModel]
    read: type[SQLModel]
    text: Callable[[Any], str]
    order: tuple[str, ...]
    writer_edit_flag: bool = False


KINDS: dict[str, EntityKind] = {
    kind.name: kind
    for kind in (
        EntityKind("character", "Character", Character, CharacterCreate, CharacterUpdate, CharacterRead, _character_text, ("position", "id"), True),
        EntityKind(
            "relationship",
            "Relationship",
            CharacterRelationship,
            CharacterRelationshipCreate,
            CharacterRelationshipUpdate,
            CharacterRelationshipRead,
            _relationship_text,
            ("id",),
        ),
        EntityKind(
            "timeline_event",
            "Timeline event",
            CharacterTimelineEvent,
            CharacterTimelineEventCreate,
            CharacterTimelineEventUpdate,
            CharacterTimelineEventRead,
            _event_text,
            ("character_id", "position", "id"),
        ),
        EntityKind("location", "Location", Location, LocationCreate, LocationUpdate, LocationRead, _location_text, ("position", "id"), True),
        EntityKind("beat", "Beat", StoryBeat, StoryBeatCreate, StoryBeatUpdate, StoryBeatRead, _beat_text, ("position", "id")),
    )
}


def entity_kind(name: str) -> EntityKind:
    """Return the entity kind or raise ``Invalid`` for an unknown one."""
    try:
        return KINDS[name]
    except KeyError:
        raise Invalid(f"Unknown story entity kind {name!r}; expected one of {', '.join(KINDS)}") from None


def to_read(kind: EntityKind, row: Any) -> dict[str, Any]:
    """Serialise a row through its read schema as JSON-safe data."""
    return kind.read.model_validate(row, from_attributes=True).model_dump(mode="json")


async def list_entities(
    session: AsyncSession, project_id: int, kind_name: str, *, character_id: int | None = None
) -> list[Any]:
    """Return a project's entities of one kind in display order."""
    kind = entity_kind(kind_name)
    model: Any = kind.model
    query = select(model).where(model.project_id == project_id)
    if character_id is not None and kind.name == "timeline_event":
        query = query.where(model.character_id == character_id)
    if character_id is not None and kind.name == "relationship":
        query = query.where(
            (col(model.source_character_id) == character_id) | (col(model.target_character_id) == character_id)
        )
    for field_name in kind.order:
        query = query.order_by(col(getattr(model, field_name)))
    return list((await session.exec(query)).all())


async def get_entity(session: AsyncSession, project_id: int, kind_name: str, entity_id: int) -> Any:
    """Return one entity in project scope or raise ``NotFound``."""
    kind = entity_kind(kind_name)
    row: Any = await session.get(kind.model, entity_id)
    if row is None or row.project_id != project_id:
        raise NotFound(f"{kind.label} not found")
    return row


async def _owned(session: AsyncSession, model: Any, project_id: int, row_id: int) -> bool:
    """Return whether a row belongs to the project (directly or via its screenplay)."""
    if model is Scene:
        query = (
            select(Scene.id)
            .join(Act, onclause=col(Scene.act_id) == col(Act.id))
            .join(Screenplay, onclause=col(Act.screenplay_id) == col(Screenplay.id))
            .where(Scene.id == row_id, Screenplay.project_id == project_id)
        )
        return (await session.exec(query)).first() is not None
    if model is Act:
        query = (
            select(Act.id)
            .join(Screenplay, onclause=col(Act.screenplay_id) == col(Screenplay.id))
            .where(Act.id == row_id, Screenplay.project_id == project_id)
        )
        return (await session.exec(query)).first() is not None
    row = await session.get(model, row_id)
    return row is not None and row.project_id == project_id


_REFERENCES: dict[str, tuple[Any, str]] = {
    "character_id": (Character, "Character"),
    "source_character_id": (Character, "Character"),
    "target_character_id": (Character, "Character"),
    "scene_id": (Scene, "Scene"),
    "beat_id": (StoryBeat, "Beat"),
    "act_id": (Act, "Act"),
}
_LIST_REFERENCES: dict[str, tuple[Any, str]] = {"scene_ids": (Scene, "Scene"), "character_ids": (Character, "Character")}


async def _validate_references(session: AsyncSession, project_id: int, values: dict[str, Any]) -> None:
    """Reject references to rows outside the project."""
    for field_name, (model, label) in _REFERENCES.items():
        value = values.get(field_name)
        if value is not None and not await _owned(session, model, project_id, int(value)):
            raise NotFound(f"{label} {value} is not in this project")
    for field_name, (model, label) in _LIST_REFERENCES.items():
        for value in values.get(field_name) or []:
            if not await _owned(session, model, project_id, int(value)):
                raise NotFound(f"{label} {value} is not in this project")
    if values.get("source_character_id") is not None and values.get("source_character_id") == values.get(
        "target_character_id"
    ):
        raise Invalid("A relationship needs two different characters")


def validate_input(schema: type[BaseModel], data: BaseModel | dict[str, Any]) -> BaseModel:
    """Validate input against a schema, turning validation errors into ``Invalid``."""
    if isinstance(data, dict) and (unknown := sorted(set(data) - set(schema.model_fields))):
        # Agents send plain dicts; name the fields they may use instead of silently dropping theirs.
        raise Invalid(f"Unknown field(s) {', '.join(unknown)}; allowed: {', '.join(schema.model_fields)}")
    try:
        return schema.model_validate(data.model_dump(exclude_unset=True) if isinstance(data, BaseModel) else data)
    except ValidationError as exc:
        raise Invalid(str(exc)) from exc


async def _after_change(project_id: int, kind: EntityKind, row: Any, action: str) -> None:
    """Publish the change and refresh the entity's RAG document."""
    source_id = f"{kind.name}:{row.id}"
    if action == "deleted":
        await indexing.delete_document(project_id, source_id)
    else:
        await indexing.index_document(project_id, source_id, kind.name, kind.text(row), row.version)
    await events.publish(
        project_id, "story.changed", {"kind": kind.name, "id": row.id, "version": row.version, "action": action}
    )


async def create_entity(
    session: AsyncSession,
    project_id: int,
    kind_name: str,
    data: BaseModel | dict[str, Any],
    *,
    source: str = "writer",
) -> Any:
    """Validate and create one entity; return the persisted row."""
    kind = entity_kind(kind_name)
    parsed = validate_input(kind.create, data)
    values = parsed.model_dump()
    await _validate_references(session, project_id, values)
    model: Any = kind.model
    if "position" in values and not isinstance(values.get("position"), int):
        values["position"] = 0
    row = model(project_id=project_id, **values)
    if hasattr(row, "source"):
        row.source = source
    if kind.writer_edit_flag:
        row.writer_edited = source == "writer"
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await _after_change(project_id, kind, row, "created")
    return row


async def update_entity(
    session: AsyncSession,
    project_id: int,
    kind_name: str,
    entity_id: int,
    data: BaseModel | dict[str, Any],
    *,
    expected_version: int | None,
    source: str = "writer",
    require_version: bool = True,
) -> Any:
    """Apply a partial update when the caller holds the current version."""
    kind = entity_kind(kind_name)
    row = await get_entity(session, project_id, kind_name, entity_id)
    check_version(expected_version, row.version, kind.label, required=require_version)
    changes = validate_input(kind.update, data).model_dump(exclude_unset=True)
    await _validate_references(session, project_id, changes)
    for key, value in changes.items():
        setattr(row, key, value)
    if kind.writer_edit_flag and source == "writer":
        row.writer_edited = True
    row.version += 1
    row.updated_at = datetime.now(UTC)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await _after_change(project_id, kind, row, "updated")
    return row


async def delete_entity(
    session: AsyncSession,
    project_id: int,
    kind_name: str,
    entity_id: int,
    *,
    expected_version: int | None,
    require_version: bool = True,
) -> dict[str, Any]:
    """Delete one entity (children cascade); return its last state."""
    kind = entity_kind(kind_name)
    row = await get_entity(session, project_id, kind_name, entity_id)
    check_version(expected_version, row.version, kind.label, required=require_version)
    snapshot = to_read(kind, row)
    if kind.name == "character":
        # Detach the character from beats that list them; relationships and events cascade.
        for beat in await list_entities(session, project_id, "beat"):
            if entity_id in beat.character_ids:
                beat.character_ids = [item for item in beat.character_ids if item != entity_id]
                beat.version += 1
                session.add(beat)
    await session.delete(row)
    await session.commit()
    await _after_change(project_id, kind, row, "deleted")
    return snapshot


def editable_fields(kind_name: str) -> list[str]:
    """Return the fields a partial update may change for a kind."""
    return list(entity_kind(kind_name).update.model_fields)
