"""Top-right user menu with profile and settings popups.

State is per-browser (``app.storage.user``) — there is no authentication yet.
Profile holds a display name; settings hold placeholder LLM provider/model
preferences that Phase E will wire to the agent layer.
"""

from nicegui import app, ui

from draftpilot.ui.components.buttons import ghost_button, primary_button
from draftpilot.ui.components.inputs import select_field, text_field

# Provider ids surfaced as placeholders; the agent layer (Phase E) consumes these.
LLM_PROVIDERS = [
    "openai",
    "anthropic",
    "gemini",
    "groq",
    "mistral",
    "ollama",
    "openrouter",
    "bedrock",
    "other",
]


def _profile() -> dict[str, str]:
    """Return the persisted profile mapping, creating it if absent."""
    return app.storage.user.setdefault("profile", {})


def _settings() -> dict[str, str]:
    """Return the persisted settings mapping, creating it if absent."""
    return app.storage.user.setdefault("settings", {})


def _display_name() -> str:
    """Return the current display name, defaulting to ``Guest``."""
    return _profile().get("display_name") or "Guest"


def user_menu() -> None:
    """Render the avatar button + dropdown menu in the header."""
    with ui.button(icon="account_circle").props("flat round dense").style(
        "color: var(--dp-fg-muted)"
    ):
        with ui.menu().props("auto-close"):
            ui.menu_item(_display_name()).props("disable").classes("dp-muted text-sm")
            ui.separator()
            ui.menu_item("Profile", _profile_dialog)
            ui.menu_item("Settings", _settings_dialog)


def _profile_dialog() -> None:
    """Open the profile popup to view and edit the display name."""
    with ui.dialog() as dialog, ui.card().classes("min-w-[360px]"):
        ui.label("Profile").classes("text-lg font-semibold")
        name = text_field("Display name", value=_profile().get("display_name", ""))

        def save() -> None:
            """Persist the display name and close the dialog."""
            _profile()["display_name"] = (name.value or "").strip()
            dialog.close()
            ui.notify("Profile saved", type="positive")

        with ui.row().classes("justify-end w-full"):
            ghost_button("Cancel", dialog.close)
            primary_button("Save", save)
    dialog.open()


def _settings_dialog() -> None:
    """Open the settings popup for model-provider preferences."""
    current = _settings()
    with ui.dialog() as dialog, ui.card().classes("min-w-[360px]"):
        ui.label("Settings").classes("text-lg font-semibold")
        ui.label("Default model provider").classes("dp-section-title")
        provider = select_field(
            "Provider", LLM_PROVIDERS, value=current.get("llm_provider", "openai")
        )
        model = text_field("Model", value=current.get("llm_model", ""))
        ui.label("Theme is set from the header toggle.").classes("dp-muted text-xs")

        def save() -> None:
            """Persist the provider/model preferences and close the dialog."""
            current["llm_provider"] = provider.value
            current["llm_model"] = (model.value or "").strip()
            dialog.close()
            ui.notify("Settings saved", type="positive")

        with ui.row().classes("justify-end w-full"):
            ghost_button("Cancel", dialog.close)
            primary_button("Save", save)
    dialog.open()
