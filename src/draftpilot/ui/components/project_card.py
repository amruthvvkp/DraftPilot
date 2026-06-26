"""Clickable project card for the projects vault grid."""

from collections.abc import Callable
from typing import Any

from nicegui import ui

Handler = Callable[..., Any]


def project_card(
    title: str,
    subtitle: str | None = None,
    meta: str | None = None,
    icon: str = "movie",
    on_click: Handler | None = None,
) -> None:
    """Render a clickable card summarizing a project (title, logline, meta)."""
    card = ui.column().classes(
        "dp-card gap-2 w-full cursor-pointer hover:shadow-lg transition-shadow"
    )
    if on_click is not None:
        card.on("click", on_click)
    with card:
        with ui.row().classes("items-center gap-2"):
            ui.icon(icon).classes("text-primary")
            ui.label(title).classes("text-base font-semibold")
        if subtitle:
            ui.label(subtitle).classes("dp-muted text-sm")
        if meta:
            ui.label(meta).classes("dp-section-title")
