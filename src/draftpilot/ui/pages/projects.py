"""Projects vault — FinalDraft-style landing to browse and create projects."""

from collections.abc import Awaitable, Callable

from nicegui import ui

from draftpilot.core.db import session_scope
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.models import Project, ProjectCreate, ScreenplayCreate
from draftpilot.ui import components as c


async def content() -> None:
    """Render the projects vault: a create action and a grid of project cards."""
    with ui.row().classes("items-center justify-between w-full"):
        ui.label("Projects").classes("text-2xl font-bold")
        with ui.dropdown_button("Create", icon="add").props("unelevated rounded"):
            ui.item("New project", on_click=lambda: _new_project_dialog(refresh))
            ui.item("Upload screenplay", on_click=_upload_stub)

    grid = ui.row().classes("w-full gap-4 flex-wrap")

    async def refresh() -> None:
        """Reload and render the project cards from the database."""
        grid.clear()
        async with session_scope() as session:
            projects = await projects_crud.list_all(session)
            counts: dict[int, int] = {}
            for project in projects:
                assert project.id is not None
                counts[project.id] = len(
                    await screenplays_crud.list_for_project(session, project.id)
                )
        with grid:
            if not projects:
                c.empty_state(
                    "movie_creation",
                    "Start a project",
                    "Create a project to collect your screenplays, research, and media in one place.",
                    action_label="New project",
                    on_action=lambda: _new_project_dialog(refresh),
                )
                return
            for project in projects:
                assert project.id is not None
                count = counts[project.id]
                with ui.column().classes("w-72"):
                    c.project_card(
                        project.title,
                        subtitle=project.logline,
                        meta=f"{count} screenplay{'s' if count != 1 else ''}",
                        on_click=lambda p=project: _open_project_dialog(p, refresh),
                    )

    await refresh()


def _upload_stub() -> None:
    """Placeholder for screenplay import (wired up in a later phase)."""
    ui.notify("Import / upload arrives in a later phase", type="info")


async def _open_project_dialog(
    project: Project, on_done: Callable[[], Awaitable[None]]
) -> None:
    """Open a dialog listing a project's screenplays with open/add actions."""
    assert project.id is not None
    project_id = project.id
    async with session_scope() as session:
        screenplays = await screenplays_crud.list_for_project(session, project_id)
    with ui.dialog() as dialog, ui.card().classes("min-w-[420px]"):
        ui.label(project.title).classes("text-lg font-semibold")
        if project.logline:
            ui.label(project.logline).classes("dp-muted text-sm")
        if not screenplays:
            ui.label("No screenplays yet.").classes("dp-muted text-sm")
        for screenplay in screenplays:
            with ui.row().classes("items-center justify-between w-full"):
                ui.label(f"🎬 {screenplay.title}  ·  {screenplay.format}/{screenplay.status}").classes(
                    "text-sm"
                )
                c.ghost_button(
                    "Open",
                    lambda sid=screenplay.id: ui.navigate.to(f"/screenplay/{sid}"),
                    icon="edit",
                )
        with ui.row().classes("justify-end w-full"):
            c.ghost_button("Close", dialog.close)
            c.primary_button(
                "Add screenplay",
                lambda: _new_screenplay_dialog(project_id, on_done, dialog),
                icon="add",
            )
    dialog.open()


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
                    ProjectCreate(
                        title=title.value,
                        logline=logline.value or None,
                        genres=[genre.value] if genre.value else [],
                    ),
                )
            dialog.close()
            ui.notify("Project created", type="positive")
            await on_done()

        with ui.row().classes("justify-end w-full"):
            c.ghost_button("Cancel", dialog.close)
            c.primary_button("Create", save)
    dialog.open()


def _new_screenplay_dialog(
    project_id: int, on_done: Callable[[], Awaitable[None]], parent: ui.dialog | None = None
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
            if parent is not None:
                parent.close()
            ui.notify("Screenplay created", type="positive")
            await on_done()

        with ui.row().classes("justify-end w-full"):
            c.ghost_button("Cancel", dialog.close)
            c.primary_button("Create", save)
    dialog.open()
