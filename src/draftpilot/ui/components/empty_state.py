"""Centered empty-state card used when a collection has no items yet."""

from collections.abc import Callable
from typing import Any

from nicegui import ui

from draftpilot.ui.components.buttons import primary_button

Handler = Callable[..., Any]


def empty_state(
    icon: str,
    title: str,
    message: str,
    action_label: str | None = None,
    on_action: Handler | None = None,
) -> None:
    """Render a centered placeholder card with an icon, copy, and optional action."""
    with ui.column().classes(
        "dp-card w-full items-center text-center gap-3 py-10"
    ).style("border-style: dashed"):
        ui.icon(icon).classes("text-primary").style("font-size: 2.5rem")
        ui.label(title).classes("text-lg font-semibold")
        ui.label(message).classes("dp-muted text-sm max-w-md")
        if action_label and on_action is not None:
            primary_button(action_label, on_action, icon="add")
