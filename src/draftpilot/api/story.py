"""Typed story-development endpoints: storyline, characters, timelines, relationships, locations, beats, moments, variants."""

from typing import Any

from fastapi import APIRouter, Depends, Header, status
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.core.story import entities
from draftpilot.core.story.storyline import storyline
from draftpilot.core.story.structure import require_project
from draftpilot.models import (
    CharacterCreate,
    CharacterRead,
    CharacterRelationshipCreate,
    CharacterRelationshipRead,
    CharacterRelationshipUpdate,
    CharacterTimelineEventCreate,
    CharacterTimelineEventRead,
    CharacterTimelineEventUpdate,
    CharacterUpdate,
    LocationCreate,
    LocationRead,
    LocationUpdate,
    NarrativeVariantCreate,
    NarrativeVariantRead,
    NarrativeVariantUpdate,
    StoryBeatCreate,
    StoryBeatRead,
    StoryBeatUpdate,
    StoryMomentCreate,
    StoryMomentRead,
    StoryMomentUpdate,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["story"])


@router.get("/storyline")
async def read_storyline(project_id: int, session: AsyncSession = Depends(async_get_db)) -> dict[str, Any]:
    """Return the project's logline, premise, synopsis, theme, tone and outline text."""
    return storyline(await require_project(session, project_id))


async def _list(
    session: AsyncSession, project_id: int, kind: str, character_id: int | None = None, moment_id: int | None = None
) -> list[Any]:
    """List a project's entities after checking the project exists."""
    await require_project(session, project_id)
    return await entities.list_entities(session, project_id, kind, character_id=character_id, moment_id=moment_id)


# Characters ------------------------------------------------------------------------------------


@router.get("/characters", response_model=list[CharacterRead])
async def list_characters(project_id: int, session: AsyncSession = Depends(async_get_db)) -> list[Any]:
    """List characters in cast order."""
    return await _list(session, project_id, "character")


@router.post("/characters", response_model=CharacterRead, status_code=status.HTTP_201_CREATED)
async def create_character(project_id: int, data: CharacterCreate, session: AsyncSession = Depends(async_get_db)) -> Any:
    """Create a character profile."""
    await require_project(session, project_id)
    return await entities.create_entity(session, project_id, "character", data)


@router.get("/characters/{character_id}", response_model=CharacterRead)
async def read_character(project_id: int, character_id: int, session: AsyncSession = Depends(async_get_db)) -> Any:
    """Return one character."""
    return await entities.get_entity(session, project_id, "character", character_id)


@router.patch("/characters/{character_id}", response_model=CharacterRead)
async def update_character(
    project_id: int,
    character_id: int,
    data: CharacterUpdate,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> Any:
    """Update a character profile with optimistic concurrency."""
    return await entities.update_entity(session, project_id, "character", character_id, data, expected_version=if_match)


@router.delete("/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_character(
    project_id: int,
    character_id: int,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> None:
    """Delete a character with their timeline and relationships."""
    await entities.delete_entity(session, project_id, "character", character_id, expected_version=if_match)


@router.get("/characters/{character_id}/timeline", response_model=list[CharacterTimelineEventRead])
async def list_character_timeline(project_id: int, character_id: int, session: AsyncSession = Depends(async_get_db)) -> list[Any]:
    """List one character's timeline events in story order."""
    await entities.get_entity(session, project_id, "character", character_id)
    return await _list(session, project_id, "timeline_event", character_id)


# Timeline events ---------------------------------------------------------------------------------


@router.get("/timeline-events", response_model=list[CharacterTimelineEventRead])
async def list_timeline_events(
    project_id: int,
    character_id: int | None = None,
    moment_id: int | None = None,
    session: AsyncSession = Depends(async_get_db),
) -> list[Any]:
    """List character timeline events, optionally for one character or one shared moment."""
    return await _list(session, project_id, "timeline_event", character_id, moment_id)


@router.post("/timeline-events", response_model=CharacterTimelineEventRead, status_code=status.HTTP_201_CREATED)
async def create_timeline_event(
    project_id: int, data: CharacterTimelineEventCreate, session: AsyncSession = Depends(async_get_db)
) -> Any:
    """Add an event to a character's timeline."""
    await require_project(session, project_id)
    return await entities.create_entity(session, project_id, "timeline_event", data)


@router.patch("/timeline-events/{event_id}", response_model=CharacterTimelineEventRead)
async def update_timeline_event(
    project_id: int,
    event_id: int,
    data: CharacterTimelineEventUpdate,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> Any:
    """Update a timeline event with optimistic concurrency."""
    return await entities.update_entity(session, project_id, "timeline_event", event_id, data, expected_version=if_match)


@router.delete("/timeline-events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_timeline_event(
    project_id: int,
    event_id: int,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> None:
    """Delete a timeline event."""
    await entities.delete_entity(session, project_id, "timeline_event", event_id, expected_version=if_match)


# Relationships -----------------------------------------------------------------------------------


@router.get("/relationships", response_model=list[CharacterRelationshipRead])
async def list_relationships(
    project_id: int, character_id: int | None = None, session: AsyncSession = Depends(async_get_db)
) -> list[Any]:
    """List character relationships, optionally those touching one character."""
    return await _list(session, project_id, "relationship", character_id)


@router.post("/relationships", response_model=CharacterRelationshipRead, status_code=status.HTTP_201_CREATED)
async def create_relationship(
    project_id: int, data: CharacterRelationshipCreate, session: AsyncSession = Depends(async_get_db)
) -> Any:
    """Relate two characters."""
    await require_project(session, project_id)
    return await entities.create_entity(session, project_id, "relationship", data)


@router.patch("/relationships/{relationship_id}", response_model=CharacterRelationshipRead)
async def update_relationship(
    project_id: int,
    relationship_id: int,
    data: CharacterRelationshipUpdate,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> Any:
    """Update a relationship with optimistic concurrency."""
    return await entities.update_entity(session, project_id, "relationship", relationship_id, data, expected_version=if_match)


@router.delete("/relationships/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_relationship(
    project_id: int,
    relationship_id: int,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> None:
    """Delete a relationship."""
    await entities.delete_entity(session, project_id, "relationship", relationship_id, expected_version=if_match)


# Locations ---------------------------------------------------------------------------------------


@router.get("/locations", response_model=list[LocationRead])
async def list_locations(project_id: int, session: AsyncSession = Depends(async_get_db)) -> list[Any]:
    """List locations."""
    return await _list(session, project_id, "location")


@router.post("/locations", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
async def create_location(project_id: int, data: LocationCreate, session: AsyncSession = Depends(async_get_db)) -> Any:
    """Create a location."""
    await require_project(session, project_id)
    return await entities.create_entity(session, project_id, "location", data)


@router.patch("/locations/{location_id}", response_model=LocationRead)
async def update_location(
    project_id: int,
    location_id: int,
    data: LocationUpdate,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> Any:
    """Update a location with optimistic concurrency."""
    return await entities.update_entity(session, project_id, "location", location_id, data, expected_version=if_match)


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(
    project_id: int,
    location_id: int,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> None:
    """Delete a location."""
    await entities.delete_entity(session, project_id, "location", location_id, expected_version=if_match)


# Beats -------------------------------------------------------------------------------------------


@router.get("/beats", response_model=list[StoryBeatRead])
async def list_beats(project_id: int, session: AsyncSession = Depends(async_get_db)) -> list[Any]:
    """List outline beats in order."""
    return await _list(session, project_id, "beat")


@router.post("/beats", response_model=StoryBeatRead, status_code=status.HTTP_201_CREATED)
async def create_beat(project_id: int, data: StoryBeatCreate, session: AsyncSession = Depends(async_get_db)) -> Any:
    """Add an outline beat."""
    await require_project(session, project_id)
    return await entities.create_entity(session, project_id, "beat", data)


@router.patch("/beats/{beat_id}", response_model=StoryBeatRead)
async def update_beat(
    project_id: int,
    beat_id: int,
    data: StoryBeatUpdate,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> Any:
    """Update a beat (including its act, order and linked scenes) with optimistic concurrency."""
    return await entities.update_entity(session, project_id, "beat", beat_id, data, expected_version=if_match)


@router.delete("/beats/{beat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_beat(
    project_id: int,
    beat_id: int,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> None:
    """Delete a beat."""
    await entities.delete_entity(session, project_id, "beat", beat_id, expected_version=if_match)


# Shared moments --------------------------------------------------------------------------------


@router.get("/moments", response_model=list[StoryMomentRead])
async def list_moments(project_id: int, session: AsyncSession = Depends(async_get_db)) -> list[Any]:
    """List shared story moments in story-world order (undated ones last)."""
    return await _list(session, project_id, "moment")


@router.post("/moments", response_model=StoryMomentRead, status_code=status.HTTP_201_CREATED)
async def create_moment(project_id: int, data: StoryMomentCreate, session: AsyncSession = Depends(async_get_db)) -> Any:
    """Create a moment several characters share; link their events to it with ``moment_id``."""
    await require_project(session, project_id)
    return await entities.create_entity(session, project_id, "moment", data)


@router.patch("/moments/{moment_id}", response_model=StoryMomentRead)
async def update_moment(
    project_id: int,
    moment_id: int,
    data: StoryMomentUpdate,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> Any:
    """Update a shared moment with optimistic concurrency."""
    return await entities.update_entity(session, project_id, "moment", moment_id, data, expected_version=if_match)


@router.delete("/moments/{moment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_moment(
    project_id: int,
    moment_id: int,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> None:
    """Delete a shared moment; its participants' events stay, unlinked."""
    await entities.delete_entity(session, project_id, "moment", moment_id, expected_version=if_match)


# Narrative variants ------------------------------------------------------------------------------


@router.get("/narrative-variants", response_model=list[NarrativeVariantRead])
async def list_narrative_variants(project_id: int, session: AsyncSession = Depends(async_get_db)) -> list[Any]:
    """List saved narrative orders."""
    return await _list(session, project_id, "variant")


@router.post("/narrative-variants", response_model=NarrativeVariantRead, status_code=status.HTTP_201_CREATED)
async def create_narrative_variant(
    project_id: int, data: NarrativeVariantCreate, session: AsyncSession = Depends(async_get_db)
) -> Any:
    """Save a named scene order without applying it."""
    await require_project(session, project_id)
    return await entities.create_entity(session, project_id, "variant", data)


@router.patch("/narrative-variants/{variant_id}", response_model=NarrativeVariantRead)
async def update_narrative_variant(
    project_id: int,
    variant_id: int,
    data: NarrativeVariantUpdate,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> Any:
    """Rename or reorder a narrative variant with optimistic concurrency."""
    return await entities.update_entity(session, project_id, "variant", variant_id, data, expected_version=if_match)


@router.delete("/narrative-variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_narrative_variant(
    project_id: int,
    variant_id: int,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> None:
    """Delete a narrative variant."""
    await entities.delete_entity(session, project_id, "variant", variant_id, expected_version=if_match)
