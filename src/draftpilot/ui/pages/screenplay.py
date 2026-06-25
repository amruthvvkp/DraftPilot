"""Screenplay editor — manage scenes and run background analysis."""

from collections.abc import Awaitable, Callable

from nicegui import ui

from draftpilot.core.cache import cache_get
from draftpilot.core.db import session_scope
from draftpilot.core.queue import get_arq_pool
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.models import SceneCreate
from draftpilot.ui import components as c

ANALYSIS_CACHE_KEY = "analysis:{id}"


async def content(screenplay_id: int) -> None:
    """Render the screenplay editor for managing scenes and analysis."""
    screenplay_id = int(screenplay_id)
    async with session_scope() as session:
        screenplay = await screenplays_crud.get(session, screenplay_id)
    if screenplay is None:
        ui.label("Screenplay not found.").classes("text-lg")
        c.ghost_button("Back to projects", lambda: ui.navigate.to("/projects"), icon="arrow_back")
        return

    with ui.row().classes("items-center justify-between w-full"):
        ui.label(screenplay.title).classes("text-2xl font-bold")
        c.ghost_button("Back", lambda: ui.navigate.to("/projects"), icon="arrow_back")

    scene_list = ui.column().classes("w-full gap-2")

    async def refresh_scenes() -> None:
        """Reload and render the scene list from the database."""
        scene_list.clear()
        async with session_scope() as session:
            rows = await scenes_crud.list_for_screenplay(session, screenplay_id)
        with scene_list:
            if not rows:
                ui.label("No scenes yet.").classes("dp-muted")
            for scene in rows:
                with c.panel():
                    ui.label(f"{scene.position}. {scene.heading}").classes("font-semibold dp-mono")
                    if scene.body:
                        ui.label(scene.body).classes("text-sm dp-muted")

    with c.panel("Scenes"):
        await refresh_scenes()
        c.primary_button("Add scene", lambda: _new_scene_dialog(screenplay_id, refresh_scenes), icon="add")

    with c.panel("Analysis") as _:
        result_area = ui.column().classes("w-full gap-1")

        async def show_result() -> None:
            """Render the cached analysis result, if any."""
            result_area.clear()
            cached = await cache_get(ANALYSIS_CACHE_KEY.format(id=screenplay_id))
            with result_area:
                if cached is None:
                    ui.label("No analysis yet. Run it, then refresh.").classes("dp-muted")
                else:
                    for key, value in cached.items():
                        ui.label(f"{key}: {value}").classes("text-sm dp-mono")

        async def run_analysis() -> None:
            """Enqueue the screenplay analysis background job."""
            pool = await get_arq_pool()
            await pool.enqueue_job("analyze_screenplay", screenplay_id)
            ui.notify("Analysis queued — refresh in a moment", type="positive")

        with ui.row().classes("gap-2"):
            c.primary_button("Run analysis", run_analysis, icon="insights")
            c.ghost_button("Refresh result", show_result, icon="refresh")
        await show_result()


def _new_scene_dialog(
    screenplay_id: int, on_done: Callable[[], Awaitable[None]]
) -> None:
    """Open a dialog to add a scene to a screenplay, then run on_done."""
    with ui.dialog() as dialog, ui.card().classes("min-w-[420px]"):
        ui.label("New scene").classes("text-lg font-semibold")
        heading = c.text_field("Heading", placeholder="INT. COFFEE SHOP - DAY")
        position = c.text_field("Position", value="0")
        body = c.text_area("Body", placeholder="Action and dialogue…")

        async def save() -> None:
            """Validate inputs, persist the scene, and close the dialog."""
            if not heading.value:
                ui.notify("Heading is required", type="warning")
                return
            try:
                pos = int(position.value or 0)
            except ValueError:
                pos = 0
            async with session_scope() as session:
                await scenes_crud.create(
                    session,
                    SceneCreate(
                        heading=heading.value,
                        position=pos,
                        body=body.value or "",
                        screenplay_id=screenplay_id,
                    ),
                )
            dialog.close()
            ui.notify("Scene added", type="positive")
            await on_done()

        with ui.row().classes("justify-end w-full"):
            c.ghost_button("Cancel", dialog.close)
            c.primary_button("Add", save)
    dialog.open()
