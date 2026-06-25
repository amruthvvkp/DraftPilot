"""Projects page — list/create projects and their screenplays."""

from collections.abc import Awaitable, Callable

from nicegui import ui

from draftpilot.core.db import session_scope
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.models import ProjectCreate, ScreenplayCreate
from draftpilot.ui import components as c


async def content() -> None:
    """Render the projects page listing projects and their screenplays."""
    ui.label("Projects").classes("text-2xl font-bold")

    container = ui.column().classes("w-full gap-3")

    async def refresh() -> None:
        """Reload and render the project list with their screenplays."""
        container.clear()
        async with session_scope() as session:
            rows = await projects_crud.list_all(session)
            data = []
            for p in rows:
                assert p.id is not None  # persisted rows always have an id
                data.append((p, await screenplays_crud.list_for_project(session, p.id)))
        with container:
            if not data:
                ui.label("No projects yet. Create your first one.").classes("dp-muted")
            for project, screenplays in data:
                with c.panel():
                    with ui.row().classes("items-center justify-between w-full"):
                        with ui.column().classes("gap-0"):
                            ui.label(project.title).classes("text-lg font-semibold")
                            if project.logline:
                                ui.label(project.logline).classes("dp-muted text-sm")
                        c.ghost_button(
                            "Add screenplay",
                            lambda pid=project.id: _new_screenplay_dialog(pid, refresh),
                            icon="add",
                        )
                    for s in screenplays:
                        with ui.row().classes("items-center justify-between w-full pl-2"):
                            ui.label(f"🎬 {s.title}  ·  {s.format}/{s.status}").classes("text-sm")
                            c.ghost_button(
                                "Open",
                                lambda sid=s.id: ui.navigate.to(f"/screenplay/{sid}"),
                                icon="edit",
                            )

    with ui.row():
        c.primary_button("New project", lambda: _new_project_dialog(refresh), icon="add")

    await refresh()


def _new_project_dialog(on_done: Callable[[], Awaitable[None]]) -> None:
    """Open a dialog to create a project, invoking on_done after save."""
    with ui.dialog() as dialog, ui.card().classes("min-w-[360px]"):
        ui.label("New project").classes("text-lg font-semibold")
        title = c.text_field("Title", placeholder="Untitled project")
        logline = c.text_area("Logline", placeholder="A one-sentence summary…")
        genre = c.select_field("Genre", ["Drama", "Comedy", "Thriller", "Sci-Fi", "Other"])

        async def save() -> None:
            """Validate inputs, persist the project, and close the dialog."""
            if not title.value:
                ui.notify("Title is required", type="warning")
                return
            async with session_scope() as session:
                await projects_crud.create(
                    session,
                    ProjectCreate(title=title.value, logline=logline.value or None, genre=genre.value),
                )
            dialog.close()
            ui.notify("Project created", type="positive")
            await on_done()

        with ui.row().classes("justify-end w-full"):
            c.ghost_button("Cancel", dialog.close)
            c.primary_button("Create", save)
    dialog.open()


def _new_screenplay_dialog(
    project_id: int, on_done: Callable[[], Awaitable[None]]
) -> None:
    """Open a dialog to add a screenplay to a project, then run on_done."""
    with ui.dialog() as dialog, ui.card().classes("min-w-[360px]"):
        ui.label("New screenplay").classes("text-lg font-semibold")
        title = c.text_field("Title", placeholder="Untitled screenplay")
        fmt = c.select_field("Format", ["feature", "short", "pilot"], value="feature")

        async def save() -> None:
            """Validate inputs, persist the screenplay, and close the dialog."""
            if not title.value:
                ui.notify("Title is required", type="warning")
                return
            async with session_scope() as session:
                await screenplays_crud.create(
                    session,
                    ScreenplayCreate(title=title.value, format=fmt.value, project_id=project_id),
                )
            dialog.close()
            ui.notify("Screenplay created", type="positive")
            await on_done()

        with ui.row().classes("justify-end w-full"):
            c.ghost_button("Cancel", dialog.close)
            c.primary_button("Create", save)
    dialog.open()
