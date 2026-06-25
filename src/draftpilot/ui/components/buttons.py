"""Branded button helpers wrapping ``ui.button`` with consistent styling."""

from collections.abc import Callable
from typing import Any

from nicegui import ui

# NiceGUI click handlers may be sync or async and may return anything.
Handler = Callable[..., Any]


def primary_button(text: str, on_click: Handler, icon: str | None = None) -> ui.button:
    """Render a filled, rounded button for primary actions."""
    return ui.button(text, on_click=on_click, icon=icon).props("unelevated rounded")


def ghost_button(text: str, on_click: Handler, icon: str | None = None) -> ui.button:
    """Render a flat, rounded button for secondary actions."""
    return ui.button(text, on_click=on_click, icon=icon).props("flat rounded")
