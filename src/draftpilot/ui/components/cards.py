"""Card-style containers used across pages."""

from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import ui


@contextmanager
def panel(title: str | None = None) -> Iterator[None]:
    """A bordered surface card with an optional uppercase section title."""
    with ui.column().classes("dp-card w-full gap-3"):
        if title:
            ui.label(title).classes("dp-section-title")
        yield


def stat_card(label: str, value: str | int, icon: str | None = None) -> None:
    """A compact KPI/metric card."""
    with ui.column().classes("dp-card gap-1 min-w-[150px]"):
        with ui.row().classes("items-center gap-2"):
            if icon:
                ui.icon(icon).classes("text-primary")
            ui.label(label).classes("dp-section-title")
        ui.label(str(value)).classes("dp-stat-value")
