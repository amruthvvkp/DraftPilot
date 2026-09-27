"""Projects vault — FinalDraft-style landing to browse and create projects."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from nicegui import ui

from draftpilot.core.db import session_scope
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.models import Project, ReferenceKind, ScreeningType, ScreenplayCreate
from draftpilot.ui import components as c
from draftpilot.ui.project_wizard import (
    ProjectWizardData,
    build_project_create,
    reference_create_payloads,
)


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
                ui.label(
                    f"🎬 {screenplay.title}  ·  {screenplay.format}/{screenplay.status}"
                ).classes("text-sm")
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
    """Open the multi-step project creation wizard."""
    refs: list[dict[str, Any]] = []
    artwork_path: str | None = None
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl"):
        ui.label("New project").classes("text-xl font-semibold")
        ui.label(
            "Set up the creative brief now; you can refine it in the studio later."
        ).classes("dp-muted text-sm")
        with ui.stepper().props("flat animated") as stepper:
            with ui.step("Basics", icon="title"):
                title = c.text_field("Title", placeholder="Untitled project")
                logline = c.text_area("Logline", placeholder="A one-sentence summary…")
                genres = c.select_field(
                    "Genres",
                    ["Drama", "Comedy", "Thriller", "Sci-Fi", "Horror", "Other"],
                    multiple=True,
                ).props("use-chips")
                languages = c.select_field(
                    "Languages", ["English", "Spanish", "French", "German", "Other"],
                    multiple=True,
                ).props("use-chips")
            with ui.step("Story", icon="auto_stories"):
                description = c.text_area(
                    "Description", placeholder="What is this project about?"
                )
                story_outline = c.text_area(
                    "Story outline",
                    placeholder="The beginning, turning points, and ending…",
                )
                visual_style = c.text_area(
                    "Visual style", placeholder="Mood, palette, references…"
                )
                with ui.row().classes("w-full gap-3"):
                    camera_type = c.select_field(
                        "Camera type",
                        ["Digital", "Film", "Animation", "Mixed", "Other"],
                    )
                    screening_type = c.select_field(
                        "Screening", [screening.value for screening in ScreeningType]
                    )
            with ui.step("References", icon="collections_bookmark"):
                ui.label("Films, directors, places, and other touchstones.").classes(
                    "dp-muted text-sm"
                )
                reference_list = ui.column().classes("w-full gap-2")

                def render_references() -> None:
                    """Render the current typed reference rows."""
                    reference_list.clear()
                    with reference_list:
                        for index, row in enumerate(refs):
                            with ui.row().classes("w-full items-center gap-2"):
                                row["kind"] = c.select_field(
                                    "Type",
                                    [kind.value for kind in ReferenceKind],
                                    value=row["kind"].value
                                    if row.get("kind")
                                    else ReferenceKind.OTHER.value,
                                ).classes("w-32")
                                row["label"] = c.text_field(
                                    "Reference",
                                    value=row["label"].value
                                    if row.get("label")
                                    else "",
                                    placeholder="Title or person",
                                )
                                row["url"] = c.text_field(
                                    "Link",
                                    value=row["url"].value if row.get("url") else "",
                                    placeholder="https://…",
                                )
                                c.ghost_button(
                                    "",
                                    lambda i=index: remove_reference(i),
                                    icon="delete",
                                )

                def remove_reference(index: int) -> None:
                    """Remove a reference row from the wizard."""
                    refs.pop(index)
                    render_references()

                def add_reference() -> None:
                    """Append an empty typed reference row."""
                    refs.append({})
                    render_references()

                c.ghost_button("Add reference", add_reference, icon="add")
                render_references()
            with ui.step("Artwork", icon="image"):
                ui.label("Add a visual identity with a link or a local image.").classes(
                    "dp-muted text-sm"
                )
                artwork_url = c.text_field("Artwork URL", placeholder="https://…")
                preview = ui.image().classes(
                    "hidden max-h-48 rounded-lg object-contain"
                )

                def preview_url() -> None:
                    """Show a valid artwork URL in the wizard preview."""
                    if artwork_url.value and artwork_url.value.startswith(
                        ("http://", "https://")
                    ):
                        preview.set_source(artwork_url.value).classes(remove="hidden")

                artwork_url.on("change", preview_url)

                async def handle_upload(event: Any) -> None:
                    """Store an uploaded artwork file under the app's static assets."""
                    nonlocal artwork_path
                    filename = Path(str(event.name)).name
                    if not filename:
                        return
                    upload_dir = Path(__file__).parents[1] / "static" / "uploads"
                    upload_dir.mkdir(parents=True, exist_ok=True)
                    artwork_path = str(upload_dir / f"{uuid4().hex}_{filename}")
                    content = event.content.read()
                    if hasattr(content, "__await__"):
                        content = await content
                    Path(artwork_path).write_bytes(content)
                    preview.set_source(
                        f"/static/uploads/{Path(artwork_path).name}"
                    ).classes(remove="hidden")
                    ui.notify("Artwork uploaded", type="positive")

                ui.upload(
                    label="Upload artwork",
                    on_upload=handle_upload,
                    auto_upload=True,
                ).props("accept=image/* max-file-size=5242880")
            with ui.stepper_navigation():

                def next_step() -> None:
                    """Validate the current step and advance the wizard."""
                    if stepper.value in (None, "Basics") and not title.value.strip():
                        ui.notify("Title is required", type="warning")
                        return
                    stepper.next()

                async def save() -> None:
                    """Validate, persist the project and references, then open it."""
                    if not title.value.strip():
                        ui.notify("Title is required", type="warning")
                        stepper.set_value("Basics")
                        return
                    data = ProjectWizardData(
                        title=title.value,
                        logline=logline.value,
                        description=description.value,
                        genres=genres.value or [],
                        languages=languages.value or [],
                        story_outline=story_outline.value,
                        visual_style=visual_style.value,
                        camera_type=camera_type.value,
                        screening_type=screening_type.value or None,
                        artwork_url=artwork_url.value,
                        artwork_path=artwork_path,
                        references=[
                            {
                                "kind": row["kind"].value,
                                "label": row["label"].value,
                                "url": row["url"].value,
                            }
                            for row in refs
                        ],
                    )
                    async with session_scope() as session:
                        project = await projects_crud.create_with_references(
                            session,
                            build_project_create(data),
                            reference_create_payloads(0, data),
                        )
                    assert project.id is not None
                    dialog.close()
                    ui.notify("Project created", type="positive")
                    await on_done()
                    ui.navigate.to(f"/projects?project={project.id}")

                c.ghost_button("Back", stepper.previous)
                c.primary_button("Next", next_step)
                c.primary_button("Create project", save)
    dialog.open()


def _new_screenplay_dialog(
    project_id: int,
    on_done: Callable[[], Awaitable[None]],
    parent: ui.dialog | None = None,
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
                    ScreenplayCreate(
                        title=title.value, format=fmt.value, project_id=project_id
                    ),
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
