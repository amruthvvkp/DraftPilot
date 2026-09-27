"""Reusable UI component library.

Import building blocks from here so pages depend on a single, stable surface:

    from draftpilot.ui import components as c
    c.stat_card("Scenes", 12, icon="movie")
    with c.panel("Details"): ...
"""

from draftpilot.ui.components.buttons import ghost_button, primary_button
from draftpilot.ui.components.cards import panel, stat_card
from draftpilot.ui.components.empty_state import empty_state
from draftpilot.ui.components.inputs import select_field, text_area, text_field
from draftpilot.ui.components.project_card import project_card
from draftpilot.ui.components.user_menu import user_menu

__all__ = [
    "empty_state",
    "ghost_button",
    "panel",
    "primary_button",
    "project_card",
    "select_field",
    "stat_card",
    "text_area",
    "text_field",
    "user_menu",
]
