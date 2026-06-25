"""Form input helpers with consistent props."""

from nicegui import ui


def text_field(label: str, value: str = "", placeholder: str = "") -> ui.input:
    """Render a single-line outlined text input filling its container."""
    field = ui.input(label=label, value=value, placeholder=placeholder)
    field.props("outlined dense").classes("w-full")
    return field


def text_area(label: str, value: str = "", placeholder: str = "") -> ui.textarea:
    """Render an auto-growing outlined multi-line text input."""
    field = ui.textarea(label=label, value=value, placeholder=placeholder)
    field.props("outlined dense autogrow").classes("w-full")
    return field


def select_field(label: str, options: list[str], value: str | None = None) -> ui.select:
    """Render an outlined dropdown select filling its container."""
    field = ui.select(options, label=label, value=value)
    field.props("outlined dense").classes("w-full")
    return field
