"""Project resource endpoints for the DraftPilot API."""

import difflib
import json

import logfire
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.core.queue import get_arq_pool
from draftpilot.crud import acts as acts_crud
from draftpilot.crud import blocks as blocks_crud
from draftpilot.crud import dialogue_translations as translations_crud
from draftpilot.crud import scene_revisions as revisions_crud
from draftpilot.crud import project_references as references_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.models import (
    ActRead,
    BlockCreate,
    BlockRead,
    BlockUpdate,
    DialogueTranslationCreate,
    DialogueTranslationRead,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ProjectReferenceBase,
    ProjectReferenceRead,
    ProjectReferenceUpdate,
    SceneRead,
    SceneCreate,
    SceneRevisionRead,
    SceneUpdate,
    ScreenplayRead,
    validate_language_separation,
)

router = APIRouter(prefix="/projects", tags=["projects"])


async def _enqueue_rag_index(
    project_id: int, source_id: str, source_kind: str, text: str, content_version: int
) -> None:
    """Queue a bounded canonical-document refresh after a committed screenplay change."""
    try:
        await (await get_arq_pool()).enqueue_job(
            "index_rag_document",
            {
                "project_id": project_id,
                "source_id": source_id,
                "source_kind": source_kind,
                "text": text,
                "content_version": content_version,
            },
        )
    except Exception as exc:  # pragma: no cover - queue availability varies by deployment
        logfire.warning("RAG indexing enqueue skipped: {exc}", exc=str(exc))


class ProjectWorkspaceRead(BaseModel):
    """Aggregate project context needed to render the screenplay workspace."""

    project: ProjectRead
    screenplay: ScreenplayRead | None
    acts: list[ActRead]
    scenes: list[SceneRead]
    blocks: dict[int, list[BlockRead]] = Field(default_factory=dict)


class TranslationInput(BaseModel):
    """Accept editable text for one dialogue translation variant."""

    text: str
    status: str = Field(default="draft", max_length=30)


class BlockInput(BlockCreate):
    """Accept a semantic block while taking its scene from the URL."""

    scene_id: int = 0


class SceneRevisionDetail(SceneRevisionRead):
    """Return revision metadata and its immutable screenplay snapshot."""

    snapshot: dict[str, object]


class SceneRevisionRestoreRequest(BaseModel):
    """Select which scene sections a writer wants to restore."""

    sections: list[str] = Field(default_factory=lambda: ["heading", "blocks"])


class ProjectReferenceInput(BaseModel):
    """Capture a typed reference before the server assigns its project."""

    kind: str = "other"
    label: str = Field(min_length=1, max_length=300)
    url: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=1000)


class ProjectCreateRequest(ProjectCreate):
    """Accept a project brief together with typed creative references."""

    references: list[ProjectReferenceInput] = Field(default_factory=list)


class ProjectReadWithReferences(ProjectRead):
    """Return project metadata and its persisted creative references."""

    references: list[ProjectReferenceRead] = Field(default_factory=list)


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: AsyncSession = Depends(async_get_db)) -> list[ProjectRead]:
    """Return all projects ordered by title."""
    projects = await projects_crud.list_all(session)
    return [ProjectRead.model_validate(project) for project in projects]


@router.post("", response_model=ProjectReadWithReferences, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreateRequest, session: AsyncSession = Depends(async_get_db)
) -> ProjectReadWithReferences:
    """Create and return a project from the submitted creative brief."""
    project = await projects_crud.create_with_references(
        session,
        ProjectCreate.model_validate(data),
        [ProjectReferenceBase.model_validate(reference) for reference in data.references],
    )
    references = await references_crud.list_for_project(session, project.id or 0)
    return ProjectReadWithReferences(
        **ProjectRead.model_validate(project).model_dump(),
        references=[ProjectReferenceRead.model_validate(reference) for reference in references],
    )


@router.get("/{project_id}/references", response_model=list[ProjectReferenceRead])
async def list_project_references(
    project_id: int, session: AsyncSession = Depends(async_get_db)
) -> list[ProjectReferenceRead]:
    """List typed creative references within project scope."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    references = await references_crud.list_for_project(session, project_id)
    return [ProjectReferenceRead.model_validate(reference) for reference in references]


@router.patch("/{project_id}/references/{reference_id}", response_model=ProjectReferenceRead)
async def update_project_reference(
    project_id: int,
    reference_id: int,
    data: ProjectReferenceUpdate,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> ProjectReferenceRead:
    """Update one typed reference with optimistic concurrency."""
    reference = await references_crud.get(session, reference_id)
    if reference is None or reference.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
    if if_match is None:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="If-Match is required")
    if if_match != reference.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reference has changed")
    updated = await references_crud.update(session, reference, data)
    await _enqueue_rag_index(project_id, f"reference:{updated.id}", "reference", f"{updated.label}\n{updated.note or ''}", updated.version)
    return ProjectReferenceRead.model_validate(updated)


@router.delete("/{project_id}/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_reference(
    project_id: int, reference_id: int, session: AsyncSession = Depends(async_get_db)
) -> None:
    """Delete one project reference without crossing project boundaries."""
    reference = await references_crud.get(session, reference_id)
    if reference is None or reference.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
    await references_crud.delete(session, reference)
    try:
        await (await get_arq_pool()).enqueue_job(
            "delete_rag_document", {"project_id": project_id, "source_id": f"reference:{reference_id}"}
        )
    except Exception as exc:  # pragma: no cover - queue availability varies by deployment
        logfire.warning("RAG reference deletion enqueue skipped: {exc}", exc=str(exc))


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> ProjectRead:
    """Update project instructions and metadata with optimistic concurrency."""
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if if_match is None:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="If-Match is required")
    if if_match != project.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project has changed")
    changes = data.model_dump(exclude_unset=True)
    primary_language = changes.get("primary_language", project.primary_language)
    languages = changes.get("languages", project.languages)
    try:
        validate_language_separation(primary_language, languages)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return ProjectRead.model_validate(await projects_crud.update(session, project, data))


@router.get("/{project_id}/workspace", response_model=ProjectWorkspaceRead)
async def get_project_workspace(
    project_id: int, session: AsyncSession = Depends(async_get_db)
) -> ProjectWorkspaceRead:
    """Return the project and its ordered screenplay context for the editor."""
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    screenplays = await screenplays_crud.list_for_project(session, project_id)
    screenplay = screenplays[0] if screenplays else None
    acts = []
    scenes = []
    blocks: dict[int, list[BlockRead]] = {}
    if screenplay is not None and screenplay.id is not None:
        acts = await acts_crud.list_for_screenplay(session, screenplay.id)
        scenes = await scenes_crud.list_for_screenplay(session, screenplay.id)
        for scene in scenes:
            if scene.id is not None:
                scene_blocks = await blocks_crud.list_for_scene(session, scene.id)
                blocks[scene.id] = [BlockRead.model_validate(block) for block in scene_blocks]
    return ProjectWorkspaceRead(
        project=ProjectRead.model_validate(project),
        screenplay=ScreenplayRead.model_validate(screenplay) if screenplay else None,
        acts=[ActRead.model_validate(act) for act in acts],
        scenes=[SceneRead.model_validate(scene) for scene in scenes],
        blocks=blocks,
    )


@router.post(
    "/{project_id}/screenplays/{screenplay_id}/scenes",
    response_model=SceneRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_scene(
    project_id: int,
    screenplay_id: int,
    data: SceneCreate,
    session: AsyncSession = Depends(async_get_db),
) -> SceneRead:
    """Create a scene only under an act belonging to the requested screenplay."""
    project = await projects_crud.get(session, project_id)
    screenplay = await screenplays_crud.get(session, screenplay_id)
    act = await acts_crud.get(session, data.act_id)
    if (
        project is None
        or screenplay is None
        or screenplay.project_id != project_id
        or act is None
        or act.screenplay_id != screenplay_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenplay or act not found")
    scene = await scenes_crud.create(session, data)
    await _enqueue_rag_index(
        project_id, f"scene:{scene.id}", "scene", scene.heading, scene.version
    )
    return SceneRead.model_validate(scene)


@router.patch("/{project_id}/scenes/{scene_id}", response_model=SceneRead)
async def update_project_scene(
    project_id: int,
    scene_id: int,
    data: SceneUpdate,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> SceneRead:
    """Update a project scene only when the caller holds its current version."""
    scene = await scenes_crud.get(session, scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    act = await acts_crud.get(session, scene.act_id)
    if act is None or act.screenplay_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    screenplay = await screenplays_crud.get(session, act.screenplay_id)
    if screenplay is None or screenplay.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    if if_match is None:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="If-Match is required")
    if if_match != scene.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scene has changed")
    updated = await scenes_crud.update(session, scene, data)
    await _enqueue_rag_index(
        project_id, f"scene:{updated.id}", "scene", updated.heading, updated.version
    )
    return SceneRead.model_validate(updated)


@router.post("/{project_id}/scenes/{scene_id}/blocks", response_model=BlockRead, status_code=201)
async def create_project_block(
    project_id: int,
    scene_id: int,
    data: BlockInput,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> BlockRead:
    """Create a semantic screenplay block under a versioned scene."""
    scene = await scenes_crud.get(session, scene_id)
    act = await acts_crud.get(session, scene.act_id) if scene else None
    screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
    if scene is None or screenplay is None or screenplay.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    if if_match is None:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="If-Match is required")
    if if_match != scene.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scene has changed")
    block = await blocks_crud.create(
        session, BlockCreate(scene_id=scene_id, **data.model_dump(exclude={"scene_id"}))
    )
    scene.version += 1
    session.add(scene)
    await session.commit()
    await _enqueue_rag_index(
        project_id,
        f"scene:{scene.id}",
        "scene",
        f"{scene.heading}\n{block.text}",
        scene.version,
    )
    return BlockRead.model_validate(block)


@router.patch(
    "/{project_id}/scenes/{scene_id}/blocks/{block_id}", response_model=BlockRead
)
async def update_project_block(
    project_id: int,
    scene_id: int,
    block_id: int,
    data: BlockUpdate,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> BlockRead:
    """Update a semantic screenplay block with optimistic concurrency."""
    scene = await scenes_crud.get(session, scene_id)
    block = await blocks_crud.get(session, block_id)
    act = await acts_crud.get(session, scene.act_id) if scene else None
    screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
    if (
        scene is None
        or block is None
        or block.scene_id != scene_id
        or screenplay is None
        or screenplay.project_id != project_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    if if_match is None:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="If-Match is required")
    if if_match != scene.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scene has changed")
    updated = await blocks_crud.update(session, block, data)
    scene.version += 1
    session.add(scene)
    await session.commit()
    await _enqueue_rag_index(
        project_id,
        f"scene:{scene.id}",
        "scene",
        f"{scene.heading}\n{updated.text}",
        scene.version,
    )
    return BlockRead.model_validate(updated)


@router.get(
    "/{project_id}/scenes/{scene_id}/blocks/{block_id}/translations",
    response_model=list[DialogueTranslationRead],
)
async def list_dialogue_translations(
    project_id: int,
    scene_id: int,
    block_id: int,
    session: AsyncSession = Depends(async_get_db),
) -> list[DialogueTranslationRead]:
    """List linked translations for a dialogue block within its project."""
    scene = await scenes_crud.get(session, scene_id)
    block = await blocks_crud.get(session, block_id)
    act = await acts_crud.get(session, scene.act_id) if scene else None
    screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
    if (
        scene is None
        or block is None
        or block.scene_id != scene_id
        or screenplay is None
        or screenplay.project_id != project_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dialogue block not found")
    translations = await translations_crud.list_for_block(session, block_id)
    return [DialogueTranslationRead.model_validate(item) for item in translations]


@router.put(
    "/{project_id}/scenes/{scene_id}/blocks/{block_id}/translations/{language}",
    response_model=DialogueTranslationRead,
)
async def save_dialogue_translation(
    project_id: int,
    scene_id: int,
    block_id: int,
    language: str,
    data: TranslationInput,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> DialogueTranslationRead:
    """Save a dialogue variant while preserving the authoritative source block."""
    scene = await scenes_crud.get(session, scene_id)
    block = await blocks_crud.get(session, block_id)
    if scene is None or block is None or block.scene_id != scene_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dialogue block not found")
    act = await acts_crud.get(session, scene.act_id)
    screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
    if screenplay is None or screenplay.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dialogue block not found")
    if block.element_type.value != "dialogue":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Block is not dialogue")
    if if_match is None:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="If-Match is required")
    if if_match != scene.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scene has changed")
    translation = await translations_crud.upsert(
        session,
        DialogueTranslationCreate(
            block_id=block_id,
            language=language,
            text=data.text,
            status=data.status,
            source_version=scene.version,
        ),
    )
    await _enqueue_rag_index(
        project_id,
        f"translation:{translation.id}",
        "dialogue_translation",
        translation.text,
        translation.source_version,
    )
    return DialogueTranslationRead.model_validate(translation)


@router.get("/{project_id}/scenes/{scene_id}/revisions", response_model=list[SceneRevisionRead])
async def list_scene_revisions(
    project_id: int, scene_id: int, session: AsyncSession = Depends(async_get_db)
) -> list[SceneRevisionRead]:
    """List revisions only when the scene belongs to the requested project."""
    scene = await scenes_crud.get(session, scene_id)
    act = await acts_crud.get(session, scene.act_id) if scene else None
    screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
    if scene is None or screenplay is None or screenplay.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    revisions = await revisions_crud.list_for_scene(session, scene_id)
    return [SceneRevisionRead.model_validate(revision) for revision in revisions]


@router.post(
    "/{project_id}/scenes/{scene_id}/revisions",
    response_model=SceneRevisionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_scene_revision(
    project_id: int,
    scene_id: int,
    data: dict[str, str] | None = None,
    session: AsyncSession = Depends(async_get_db),
) -> SceneRevisionDetail:
    """Capture an immutable scene snapshot for diff, rollback, or naming."""
    scene = await scenes_crud.get(session, scene_id)
    act = await acts_crud.get(session, scene.act_id) if scene else None
    screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
    if scene is None or screenplay is None or screenplay.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    revision = await revisions_crud.snapshot(session, scene, (data or {}).get("message"))
    return SceneRevisionDetail.model_validate(revision)


@router.post("/{project_id}/scenes/{scene_id}/revisions/{revision_id}/restore", response_model=SceneRead)
async def restore_scene_revision(
    project_id: int,
    scene_id: int,
    revision_id: int,
    data: SceneRevisionRestoreRequest | None = None,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> SceneRead:
    """Restore a revision only when the caller holds the current scene version."""
    scene = await scenes_crud.get(session, scene_id)
    revision = await revisions_crud.get(session, revision_id)
    act = await acts_crud.get(session, scene.act_id) if scene else None
    screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
    if (
        scene is None
        or revision is None
        or revision.scene_id != scene_id
        or screenplay is None
        or screenplay.project_id != project_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
    if if_match is None:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="If-Match is required")
    if if_match != scene.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scene has changed")
    sections = set((data or SceneRevisionRestoreRequest()).sections)
    if not sections or sections - {"heading", "blocks"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid revision sections")
    await revisions_crud.restore(session, scene, revision, sections)
    return SceneRead.model_validate(scene)


@router.get(
    "/{project_id}/scenes/{scene_id}/revisions/{revision_id}/diff/{other_revision_id}",
    response_model=dict[str, object],
)
async def diff_scene_revisions(
    project_id: int,
    scene_id: int,
    revision_id: int,
    other_revision_id: int,
    session: AsyncSession = Depends(async_get_db),
) -> dict[str, object]:
    """Return a bounded unified diff between two revisions of one project scene."""
    scene = await scenes_crud.get(session, scene_id)
    first = await revisions_crud.get(session, revision_id)
    second = await revisions_crud.get(session, other_revision_id)
    act = await acts_crud.get(session, scene.act_id) if scene else None
    screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
    if (
        scene is None
        or first is None
        or second is None
        or first.scene_id != scene_id
        or second.scene_id != scene_id
        or screenplay is None
        or screenplay.project_id != project_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
    before = json.dumps(first.snapshot, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    after = json.dumps(second.snapshot, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    changes = "\n".join(
        difflib.unified_diff(
            before,
            after,
            fromfile=f"revision-{revision_id}",
            tofile=f"revision-{other_revision_id}",
        )
    )
    if len(changes) > 100_000:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Revision diff is too large")
    return {"scene_id": scene_id, "from_revision": revision_id, "to_revision": other_revision_id, "diff": changes}
