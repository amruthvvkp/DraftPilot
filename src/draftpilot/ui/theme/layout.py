"""Base page layout: header, collapsible sidebar, and theme toggle.

``apply_head`` registers fonts + the design-system stylesheet and brands Quasar
with the shared palette. ``with_layout`` wraps a page-content builder so every
route shares the same chrome. The theme has three states (dark → light → auto)
persisted in ``app.storage.user``.
"""

import functools
import inspect
from collections.abc import Callable
from pathlib import Path

from nicegui import app, ui

from draftpilot.core.config import settings
from draftpilot.ui.theme import design

_STATIC_DIR = Path(__file__).parent.parent / "static"
LOGO_URL = "/static/logo.png"
FAVICON_ICO = _STATIC_DIR / "favicon" / "favicon.ico"

# Sidebar navigation entries: (icon, label, target path).
NAV_ITEMS: list[tuple[str, str, str]] = [
    ("dashboard", "Studio", "/"),
    ("movie", "Projects", "/projects"),
    ("palette", "Design System", "/design-system"),
]

_THEME_CYCLE = {"auto": "dark", "dark": "light", "light": "auto"}
_THEME_ICON = {"auto": "brightness_auto", "dark": "dark_mode", "light": "light_mode"}

# Sidebar widths (px) for the expanded vs collapsed mini-rail.
_DRAWER_EXPANDED = 220
_DRAWER_COLLAPSED = 68


def register_assets() -> None:
    """Mount static files and inject shared fonts + stylesheet. Call once at startup."""
    app.add_static_files("/static", str(_STATIC_DIR))
    ui.add_head_html(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
        '&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'
        '<link rel="stylesheet" href="/static/styles.css">'
        # Favicon bundle (overrides NiceGUI's default tab icon).
        '<link rel="icon" type="image/svg+xml" href="/static/favicon/favicon.svg">'
        '<link rel="icon" type="image/png" sizes="96x96" href="/static/favicon/favicon-96x96.png">'
        '<link rel="shortcut icon" href="/static/favicon/favicon.ico">'
        '<link rel="apple-touch-icon" sizes="180x180" href="/static/favicon/apple-touch-icon.png">'
        '<link rel="manifest" href="/static/favicon/site.webmanifest">',
        shared=True,
    )


def _apply_theme(dark: ui.dark_mode, mode: str) -> None:
    """Apply a theme mode (auto/dark/light) to the dark-mode element."""
    dark.value = {"auto": None, "dark": True, "light": False}[mode]


def _build_header(
    dark: ui.dark_mode, drawer: ui.left_drawer, labels: list[ui.item_label]
) -> None:
    """Render the page header: sidebar toggle, logo, title, and theme toggle."""
    with ui.header().classes("items-center justify-between px-4 py-2"):
        with ui.row().classes("items-center gap-2"):
            menu = ui.button(icon="menu").props("flat round dense color=white")
            menu.on_click(lambda: _toggle_sidebar(drawer, labels))
            menu.tooltip("Collapse / expand sidebar")
            ui.image(LOGO_URL).classes("w-7 h-8").props("no-spinner")
            ui.label(settings.ui.title).classes("text-lg font-semibold")
        toggle = ui.button(icon=_THEME_ICON[_current_mode()]).props(
            "flat round dense color=white"
        )

        def cycle() -> None:
            """Advance the theme to the next mode and persist it."""
            mode = _THEME_CYCLE[_current_mode()]
            app.storage.user["theme"] = mode
            _apply_theme(dark, mode)
            toggle.props(f"icon={_THEME_ICON[mode]} color=white")

        toggle.on_click(cycle)
        toggle.tooltip("Toggle theme (auto / dark / light)")


def _current_mode() -> str:
    """Return the persisted theme mode, defaulting to ``auto``."""
    return app.storage.user.get("theme", "auto")


def _collapsed() -> bool:
    """Return the persisted sidebar-collapsed state (default expanded)."""
    return bool(app.storage.user.get("sidebar_collapsed", False))


def _apply_sidebar(
    drawer: ui.left_drawer, labels: list[ui.item_label], collapsed: bool
) -> None:
    """Set drawer width and label visibility for the given collapsed state."""
    drawer.props(f"width={_DRAWER_COLLAPSED if collapsed else _DRAWER_EXPANDED}")
    for label in labels:
        if collapsed:
            label.classes(add="dp-nav-label--hidden")
        else:
            label.classes(remove="dp-nav-label--hidden")


def _toggle_sidebar(drawer: ui.left_drawer, labels: list[ui.item_label]) -> None:
    """Flip and persist the sidebar collapsed state (mini-rail)."""
    collapsed = not _collapsed()
    app.storage.user["sidebar_collapsed"] = collapsed
    _apply_sidebar(drawer, labels, collapsed)


def _build_sidebar() -> tuple[ui.left_drawer, list[ui.item_label]]:
    """Render the collapsible mini-rail navigation sidebar from ``NAV_ITEMS``."""
    labels: list[ui.item_label] = []
    with ui.left_drawer(bordered=True).classes("dp-sidebar").props(
        f"width={_DRAWER_EXPANDED}"
    ) as drawer:
        with ui.list().classes("w-full"):
            for icon, label, path in NAV_ITEMS:
                with ui.item(on_click=lambda p=path: ui.navigate.to(p)).classes(
                    "rounded-lg no-wrap"
                ):
                    with ui.item_section().props("avatar"):
                        ui.icon(icon)
                    with ui.item_section():
                        labels.append(ui.item_label(label).classes("dp-nav-label text-sm"))
    _apply_sidebar(drawer, labels, _collapsed())
    return drawer, labels


def with_layout(content: Callable[..., object]) -> Callable[..., object]:
    """Wrap a page-content builder with the shared header + sidebar + theme.

    Supports both sync and ``async`` content builders; positional path
    parameters (e.g. NiceGUI route params) are forwarded to ``content``.
    """

    @functools.wraps(content)
    async def wrapper(*args: object, **kwargs: object) -> None:
        """Build the chrome and render the wrapped page content."""
        ui.colors(**design.quasar_colors())
        dark = ui.dark_mode()
        _apply_theme(dark, _current_mode())
        drawer, labels = _build_sidebar()
        _build_header(dark, drawer, labels)
        with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-4"):
            result = content(*args, **kwargs)
            if inspect.isawaitable(result):
                await result

    return wrapper
