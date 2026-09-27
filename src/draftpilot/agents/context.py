"""Assemble the layered context every room agent receives: instructions and both twins."""

from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.twins import story_twin_brief, writer_twin_brief
from draftpilot.crud import projects as projects_crud


@dataclass(frozen=True)
class RoomContext:
    """The project instruction plus the Writer and Story twin briefs."""

    project_instruction: str
    writer_brief: str
    story_brief: str


async def load_room_context(session: AsyncSession, project_id: int) -> RoomContext:
    """Load a project's instruction and both twin briefs."""
    project = await projects_crud.get(session, project_id)
    return RoomContext(
        project_instruction=project.project_instruction if project else "",
        writer_brief=await writer_twin_brief(session, project_id),
        story_brief=await story_twin_brief(session, project_id),
    )
