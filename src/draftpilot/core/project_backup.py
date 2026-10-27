"""Serialise a whole project to a portable payload and restore it into a new project.

Database ids never leave the payload as references: artifacts keep a ``backup_id`` for their
dependency links, story entities keep theirs for cross references, and scenes/acts are referred
to by their (draft, ordinal) position so links survive re-creation.
"""

from typing import Any

import logfire
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import temporal
from draftpilot.core.errors import NotFound
from draftpilot.core.screenplay.hydrate import load_screenplay_doc, save_screenplay_doc
from draftpilot.core.screenplay.schema import ScreenplayDoc
from draftpilot.core.story import entities
from draftpilot.crud import acts as acts_crud
from draftpilot.crud import project_references as references_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.models import (
    Character,
    CharacterRelationship,
    CharacterTimelineEvent,
    Location,
    Project,
    ProjectCreate,
    ProjectReference,
    Screenplay,
    StoryArtifact,
    StoryBeat,
)

_STORY_ORDER = ("character", "location", "beat", "timeline_event", "relationship")
_DERIVED_FIELDS = ("cue", "dialogue_lines", "source", "writer_edited", "heading_location", "int_ext", "times")
_REF_FIELDS = {"character_id", "source_character_id", "target_character_id", "beat_id"}


async def _structure_keys(session: AsyncSession, project_id: int) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Map scene and act ids to their ``[draft index, ordinal]`` position in the project."""
    scenes: dict[int, list[int]] = {}
    acts: dict[int, list[int]] = {}
    for draft_index, screenplay in enumerate(await screenplays_crud.list_for_project(session, project_id)):
        for ordinal, act in enumerate(await acts_crud.list_for_screenplay(session, screenplay.id or 0)):
            acts[act.id or 0] = [draft_index, ordinal]
        for ordinal, scene in enumerate(await scenes_crud.list_for_screenplay(session, screenplay.id or 0)):
            scenes[scene.id or 0] = [draft_index, ordinal]
    return scenes, acts


async def _story_payload(session: AsyncSession, project_id: int) -> dict[str, list[dict[str, Any]]]:
    """Serialise typed story entities with portable references."""
    scene_keys, act_keys = await _structure_keys(session, project_id)
    payload: dict[str, list[dict[str, Any]]] = {}
    for kind_name in _STORY_ORDER:
        kind = entities.entity_kind(kind_name)
        rows = []
        for row in await entities.list_entities(session, project_id, kind_name):
            values = kind.create.model_validate(row, from_attributes=True).model_dump(mode="json")
            values.update({name: getattr(row, name) for name in _DERIVED_FIELDS if hasattr(row, name)})
            values["backup_id"] = row.id
            if "scene_ids" in values:
                values["scene_ids"] = [scene_keys[item] for item in values["scene_ids"] if item in scene_keys]
            if values.get("scene_id") is not None:
                values["scene_id"] = scene_keys.get(values["scene_id"])
            if values.get("act_id") is not None:
                values["act_id"] = act_keys.get(values["act_id"])
            rows.append(values)
        payload[kind_name] = rows
    return payload


async def project_payload(session: AsyncSession, project_id: int) -> dict[str, Any]:
    """Serialise supported project content without database identifiers."""
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise NotFound("Project not found")
    references = await references_crud.list_for_project(session, project_id)
    artifacts = await artifacts_crud.list_for_project(session, project_id)
    screenplays = await screenplays_crud.list_for_project(session, project_id)
    screenplay_payload: list[dict[str, Any]] = []
    for screenplay in screenplays:
        if screenplay.id is not None:
            screenplay_payload.append(
                {
                    "title": screenplay.title,
                    "format": screenplay.format,
                    "status": screenplay.status,
                    "document": (await load_screenplay_doc(session, screenplay.id)).model_dump(mode="json"),
                }
            )
    return {
        "project": ProjectCreate.model_validate(project).model_dump(mode="json"),
        "references": [ProjectReference.model_validate(reference).model_dump(mode="json") for reference in references],
        "artifacts": [
            {
                "backup_id": artifact.id,
                "kind": artifact.kind,
                "title": artifact.title,
                "content": artifact.content,
                "version": artifact.version,
                "stale": artifact.stale,
                "depends_on": artifact.depends_on,
                "artifact_metadata": artifact.artifact_metadata,
            }
            for artifact in artifacts
        ],
        "screenplays": screenplay_payload,
        "story": await _story_payload(session, project_id),
    }


async def _restore_story(session: AsyncSession, project_id: int, story: dict[str, Any]) -> None:
    """Recreate story entities, remapping their cross references to the new ids."""
    scene_keys, act_keys = await _structure_keys(session, project_id)
    scene_by_key = {tuple(key): scene_id for scene_id, key in scene_keys.items()}
    act_by_key = {tuple(key): act_id for act_id, key in act_keys.items()}
    new_ids: dict[str, dict[int, int]] = {}
    models: dict[str, Any] = {
        "character": Character,
        "location": Location,
        "beat": StoryBeat,
        "timeline_event": CharacterTimelineEvent,
        "relationship": CharacterRelationship,
    }
    parents = {"character_id": "character", "source_character_id": "character", "target_character_id": "character", "beat_id": "beat"}
    for kind_name in _STORY_ORDER:
        mapping = new_ids.setdefault(kind_name, {})
        for item in story.get(kind_name, []):
            values = dict(item)
            backup_id = values.pop("backup_id", None)
            if "scene_ids" in values:
                values["scene_ids"] = [scene_by_key[tuple(key)] for key in values["scene_ids"] if tuple(key) in scene_by_key]
            if values.get("scene_id") is not None:
                values["scene_id"] = scene_by_key.get(tuple(values["scene_id"]))
            if values.get("act_id") is not None:
                values["act_id"] = act_by_key.get(tuple(values["act_id"]))
            if "character_ids" in values:
                values["character_ids"] = [new_ids["character"][ref] for ref in values["character_ids"] if ref in new_ids["character"]]
            skip = False
            for field_name in _REF_FIELDS & values.keys():
                ref = values[field_name]
                if ref is None:
                    continue
                remapped = new_ids.get(parents[field_name], {}).get(ref)
                if remapped is None and field_name != "beat_id":
                    skip = True
                values[field_name] = remapped
            if skip:
                continue
            row = models[kind_name](project_id=project_id, **values)
            session.add(row)
            await session.flush()
            if isinstance(backup_id, int) and row.id is not None:
                mapping[backup_id] = row.id


async def restore_payload(session: AsyncSession, payload: dict[str, Any]) -> Project:
    """Restore validated backup content into a new project without overwriting existing data."""
    project = Project.model_validate(ProjectCreate.model_validate(payload["project"]))
    session.add(project)
    await session.flush()
    assert project.id is not None
    for reference in payload.get("references", []):
        session.add(ProjectReference(project_id=project.id, **reference))
    artifact_ids: dict[int, int] = {}
    pending_dependencies: list[tuple[StoryArtifact, list[int]]] = []
    for artifact in payload.get("artifacts", []):
        values = dict(artifact)
        backup_id = values.pop("backup_id", None)
        dependencies = values.pop("depends_on", [])
        restored = StoryArtifact(project_id=project.id, depends_on=[], **values)
        session.add(restored)
        await session.flush()
        if isinstance(backup_id, int) and restored.id is not None:
            artifact_ids[backup_id] = restored.id
        if isinstance(dependencies, list):
            pending_dependencies.append((restored, [item for item in dependencies if isinstance(item, int)]))
    for restored, dependencies in pending_dependencies:
        restored.depends_on = [artifact_ids[item] for item in dependencies if item in artifact_ids]
        session.add(restored)
    await session.commit()
    for screenplay_data in payload.get("screenplays", []):
        screenplay = Screenplay(
            project_id=project.id,
            title=screenplay_data["title"],
            format=screenplay_data["format"],
            status=screenplay_data["status"],
        )
        session.add(screenplay)
        await session.flush()
        assert screenplay.id is not None
        await save_screenplay_doc(
            session, screenplay.id, ScreenplayDoc.model_validate(screenplay_data["document"]), commit=False
        )
    await session.flush()
    if payload.get("story"):  # backups made before typed story entities have none
        await _restore_story(session, project.id, payload["story"])
    await session.commit()
    return project


async def enqueue_restored_documents(session: AsyncSession, project_id: int) -> None:
    """Queue restored artifacts and story entities for project-scoped indexing."""
    try:
        for artifact in await artifacts_crud.list_for_project(session, project_id):
            if artifact.id is None:
                continue
            await temporal.start_job(
                "index_rag_document",
                {
                    "project_id": project_id,
                    "source_id": f"artifact:{artifact.id}",
                    "source_kind": artifact.kind,
                    "text": artifact.content,
                    "content_version": artifact.version,
                },
            )
        for kind_name in _STORY_ORDER:
            kind = entities.entity_kind(kind_name)
            for row in await entities.list_entities(session, project_id, kind_name):
                await temporal.start_job(
                    "index_rag_document",
                    {
                        "project_id": project_id,
                        "source_id": f"{kind_name}:{row.id}",
                        "source_kind": kind_name,
                        "text": kind.text(row),
                        "content_version": row.version,
                    },
                )
    except Exception as exc:  # noqa: BLE001 - Temporal availability varies by deployment
        logfire.warning("Restored document indexing enqueue skipped: {exc}", exc=str(exc))
