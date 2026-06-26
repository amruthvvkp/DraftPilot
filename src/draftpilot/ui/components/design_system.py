"""Living style guide: renders every reusable component in one place.

Acts as both documentation and a visual regression surface — add a component to
the library, then showcase it here.
"""

from nicegui import ui

from draftpilot.ui import components as c
from draftpilot.ui.theme import design


def content() -> None:
    """Render the living style guide showcasing every reusable component."""
    ui.label("Design System").classes("text-2xl font-bold")
    ui.label("Reusable building blocks for the DraftPilot studio UI.").classes("dp-muted")

    with c.panel("Color tokens"):
        with ui.row().classes("gap-3 flex-wrap"):
            for name, value in design.quasar_colors().items():
                with ui.column().classes("items-center gap-1"):
                    ui.element("div").classes("rounded-lg").style(
                        f"width:48px;height:48px;background:{value};"
                        "border:1px solid var(--dp-border)"
                    )
                    ui.label(name).classes("text-xs dp-muted")

    with c.panel("Buttons"):
        with ui.row().classes("gap-3 items-center"):
            c.primary_button("Primary", lambda: ui.notify("primary"), icon="bolt")
            c.ghost_button("Ghost", lambda: ui.notify("ghost"), icon="circle")

    with c.panel("Stat cards"):
        with ui.row().classes("gap-3 flex-wrap"):
            c.stat_card("Projects", 4, icon="movie")
            c.stat_card("Screenplays", 9, icon="description")
            c.stat_card("Scenes", 132, icon="theaters")

    with c.panel("Form inputs"):
        c.text_field("Title", placeholder="Untitled project")
        c.select_field("Genre", ["Drama", "Comedy", "Thriller", "Sci-Fi"], value="Drama")
        c.text_area("Logline", placeholder="A one-sentence summary…")

    with c.panel("Project cards"):
        with ui.row().classes("gap-4 flex-wrap"):
            with ui.column().classes("w-72"):
                c.project_card(
                    "The Last Reel",
                    subtitle="A projectionist guards the final film print.",
                    meta="3 screenplays",
                    on_click=lambda: ui.notify("card click"),
                )

    with c.panel("Empty state"):
        c.empty_state(
            "movie_creation",
            "Start a project",
            "Create a project to collect your screenplays, research, and media.",
            action_label="New project",
            on_action=lambda: ui.notify("new project"),
        )

    with c.panel("User menu"):
        ui.label("Rendered top-right in the header; opens profile/settings popups.").classes(
            "dp-muted text-sm"
        )
        c.user_menu()

    with c.panel("Typography"):
        ui.label("Heading / Inter 700").classes("text-xl font-bold")
        ui.label("Body / Inter 400").classes("text-base")
        ui.label("Mono / JetBrains Mono").classes("dp-mono text-sm")
