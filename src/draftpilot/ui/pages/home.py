"""Studio dashboard — at-a-glance counts across the workspace."""

from sqlalchemy import func
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nicegui import ui

from draftpilot.core.db import session_scope
from draftpilot.models import Project, Scene, Screenplay
from draftpilot.ui import components as c


async def _count(session: AsyncSession, model: type[SQLModel]) -> int:
    """Return the total number of rows for the given model."""
    result = await session.exec(select(func.count()).select_from(model))
    return int(result.one())


async def content() -> None:
    """Render the studio dashboard with workspace-wide entity counts."""
    ui.label("Studio").classes("text-2xl font-bold")
    ui.label("Your screenplay workspace at a glance.").classes("dp-muted")

    async with session_scope() as session:
        projects = await _count(session, Project)
        screenplays = await _count(session, Screenplay)
        scenes = await _count(session, Scene)

    with ui.row().classes("gap-3 flex-wrap"):
        c.stat_card("Projects", projects, icon="movie")
        c.stat_card("Screenplays", screenplays, icon="description")
        c.stat_card("Scenes", scenes, icon="theaters")

    with c.panel("Get started"):
        ui.label("Create a project, add a screenplay, write scenes, then run analysis.").classes(
            "dp-muted"
        )
        c.primary_button("Go to Projects", lambda: ui.navigate.to("/projects"), icon="arrow_forward")
