"""Story twin and Writer twin endpoints."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import events
from draftpilot.core.db import async_get_db
from draftpilot.core.twins import (
    get_writer_profile,
    learned_decisions,
    refresh_story_twin,
    story_twin_brief,
    working_screenplay,
    writer_twin_brief,
)
from draftpilot.crud import knowledge_graph as graph_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.models import (
    KnowledgeNodeRead,
    WriterMemory,
    WriterMemoryBase,
    WriterMemoryRead,
    WriterProfileBase,
    WriterProfileRead,
)

project_router = APIRouter(prefix="/projects/{project_id}/twin", tags=["twins"])
writer_router = APIRouter(prefix="/writer", tags=["twins"])


class StoryTwinRead(BaseModel):
    """The Story twin: characters, locations, canon, and the brief agents receive."""

    screenplay_id: int | None
    characters: list[KnowledgeNodeRead]
    locations: list[KnowledgeNodeRead]
    canon: list[KnowledgeNodeRead]
    brief: str


async def _require_project(session: AsyncSession, project_id: int) -> None:
    """Raise 404 when the project does not exist."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@project_router.get("", response_model=StoryTwinRead)
async def read_story_twin(project_id: int, session: AsyncSession = Depends(async_get_db)) -> StoryTwinRead:
    """Return the Story twin, ranked: characters by dialogue, locations by scene count."""
    await _require_project(session, project_id)
    nodes = [KnowledgeNodeRead.model_validate(node, from_attributes=True) for node in await graph_crud.list_nodes(session, project_id)]
    draft = await working_screenplay(session, project_id)
    return StoryTwinRead(
        screenplay_id=draft.id if draft else None,
        characters=sorted(
            (node for node in nodes if node.kind == "character"),
            key=lambda node: -int(node.node_metadata.get("dialogue_lines", 0)),
        ),
        locations=sorted(
            (node for node in nodes if node.kind == "location"),
            key=lambda node: -len(node.node_metadata.get("scene_ids", [])),
        ),
        canon=[node for node in nodes if node.kind not in {"character", "location"}],
        brief=await story_twin_brief(session, project_id),
    )


@project_router.post("/refresh")
async def refresh(project_id: int, session: AsyncSession = Depends(async_get_db)) -> dict[str, int]:
    """Re-derive the Story twin from the working draft now."""
    await _require_project(session, project_id)
    counts = await refresh_story_twin(session, project_id)
    await events.publish(project_id, "twin.changed", counts)
    return counts


@writer_router.get("/profile", response_model=WriterProfileRead)
async def read_profile(session: AsyncSession = Depends(async_get_db)) -> WriterProfileRead:
    """Return the writer profile the room writes for."""
    return WriterProfileRead.model_validate(await get_writer_profile(session), from_attributes=True)


@writer_router.put("/profile", response_model=WriterProfileRead)
async def save_profile(data: WriterProfileBase, session: AsyncSession = Depends(async_get_db)) -> WriterProfileRead:
    """Replace the writer profile."""
    profile = await get_writer_profile(session)
    for key, value in data.model_dump().items():
        setattr(profile, key, value)
    profile.updated_at = datetime.now(UTC)
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return WriterProfileRead.model_validate(profile, from_attributes=True)


@writer_router.get("/memories", response_model=list[WriterMemoryRead])
async def list_memories(project_id: int | None = None, session: AsyncSession = Depends(async_get_db)) -> list[WriterMemoryRead]:
    """List writer memories: global ones, plus a project's when given."""
    rows = (await session.exec(select(WriterMemory).order_by(col(WriterMemory.pinned).desc(), col(WriterMemory.id).desc()))).all()
    return [
        WriterMemoryRead.model_validate(row, from_attributes=True)
        for row in rows
        if row.project_id is None or row.project_id == project_id
    ]


class MemoryInput(WriterMemoryBase):
    """Accept a new writer memory."""

    text: str = Field(min_length=1, max_length=2000)


@writer_router.post("/memories", response_model=WriterMemoryRead, status_code=status.HTTP_201_CREATED)
async def add_memory(data: MemoryInput, session: AsyncSession = Depends(async_get_db)) -> WriterMemoryRead:
    """Remember something about how the writer works."""
    memory = WriterMemory.model_validate(data.model_dump())
    session.add(memory)
    await session.commit()
    await session.refresh(memory)
    return WriterMemoryRead.model_validate(memory, from_attributes=True)


@writer_router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_memory(memory_id: int, session: AsyncSession = Depends(async_get_db)) -> None:
    """Forget one writer memory."""
    memory = await session.get(WriterMemory, memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    await session.delete(memory)
    await session.commit()


@writer_router.get("/brief")
async def brief(project_id: int | None = None, session: AsyncSession = Depends(async_get_db)) -> dict[str, Any]:
    """Return the Writer twin brief agents receive, and the decisions it learned from."""
    return {
        "brief": await writer_twin_brief(session, project_id),
        "decisions": await learned_decisions(session, project_id),
    }
