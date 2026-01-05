"""Main application entry point for DraftPilot."""

from nicegui import app, ui

from draftpilot.app.lifespan import setup_lifespan_handlers
from draftpilot.core.config import settings
from draftpilot.mcp.server import mcp

__all__ = ["app"]

# Note: NICEGUI_REDIS_URL is set automatically by Settings model_validator
# If nicegui_redis_url is None, NiceGUI uses file-based storage (default for local dev)

# Configure Logfire instrumentation on NiceGUI's FastAPI app
from draftpilot.core.logging import configure_logfire

configure_logfire(app)

# Mount FastMCP server on NiceGUI's app
app.mount(settings.mcp_mount_path, mcp.http_app())

# Setup lifespan handlers (startup/shutdown)
setup_lifespan_handlers(app)


@ui.page("/")
async def main_page():
    """Main application page with counter and LLM chat panel."""
    with ui.column().classes("w-full max-w-4xl mx-auto p-4 gap-4"):
        # Header
        ui.label("DraftPilot").classes("text-3xl font-bold")

        # Counter section
        with ui.card().classes("w-full"):
            ui.label("Counter Example").classes("text-xl font-semibold mb-2")
            counter = ui.number("Counter", value=0).classes("mb-2")

            counter_display = ui.label()
            counter_display.bind_text_from(counter, "value", lambda v: f"Counter: {v}")

            with ui.row():
                ui.button(
                    "Increment",
                    on_click=lambda: counter.set_value(counter.value + 1),
                )
                ui.button(
                    "Decrement",
                    on_click=lambda: counter.set_value(counter.value - 1),
                )

        # LLM Chat Panel
        with ui.card().classes("w-full"):
            ui.label("LLM Chat (Test Integration)").classes(
                "text-xl font-semibold mb-4"
            )

            # Model selection
            with ui.row().classes("w-full items-center gap-4 mb-4"):
                ui.label("Provider:").classes("w-24")
                provider_select = ui.select(
                    {
                        "openai": "OpenAI",
                        "anthropic": "Anthropic",
                        "google": "Google",
                        "ollama": "Ollama",
                        "deepseek": "DeepSeek",
                        "together": "Together AI",
                    },
                    value="ollama",
                    label="LLM Provider",
                ).classes("flex-1")

                ui.label("Model:").classes("w-16")
                model_select = ui.select(
                    {},
                    label="Model Name",
                    with_input=True,
                ).classes("flex-1")

            # Loading indicator for models
            models_loading = ui.spinner(size="sm", color="primary").classes("hidden")
            models_loading_label = ui.label("Loading models...").classes(
                "text-sm text-gray-500 hidden"
            )

            # Message input
            with ui.row().classes("w-full items-end gap-2 mb-4"):
                message_input = ui.textarea(
                    label="Message",
                    placeholder="Type your message here...",
                ).classes("flex-1")
                send_button = ui.button("Send", icon="send").classes("mb-4")

            # Response display
            ui.label("Response:").classes("text-sm font-semibold mb-2")
            response_area = ui.markdown().classes(
                "w-full min-h-32 p-4 bg-gray-100 rounded border"
            )

            # Status label
            status_label = ui.label("Ready").classes("text-sm text-gray-500 mt-2")

            async def load_models(provider: str):
                """Load available models for the selected provider.

                :param provider: The LLM provider name.
                """
                models_loading.set_visibility(True)
                models_loading_label.set_visibility(True)
                model_select.set_options({})
                model_select.set_value(None)

                try:
                    if provider == "ollama":
                        # Fetch models from Ollama API
                        import httpx

                        # Remove /v1 suffix if present to get base Ollama URL
                        ollama_base = settings.ollama.base_url.replace("/v1", "")

                        async with httpx.AsyncClient(timeout=5.0) as client:
                            response = await client.get(f"{ollama_base}/api/tags")
                            if response.status_code == 200:
                                data = response.json()
                                models_dict = {
                                    model["name"]: model["name"]
                                    for model in data.get("models", [])
                                }
                                if models_dict:
                                    model_select.set_options(models_dict)
                                    # Select first model by default
                                    first_model = list(models_dict.keys())[0]
                                    model_select.set_value(first_model)
                                else:
                                    model_select.set_options({"": "No models found"})
                            else:
                                model_select.set_options(
                                    {"": f"Error: {response.status_code}"}
                                )
                    elif provider == "openai":
                        # Common OpenAI models
                        model_select.set_options(
                            {
                                "gpt-4o": "GPT-4o",
                                "gpt-4o-mini": "GPT-4o Mini",
                                "gpt-4-turbo": "GPT-4 Turbo",
                                "gpt-4": "GPT-4",
                                "gpt-3.5-turbo": "GPT-3.5 Turbo",
                            }
                        )
                    elif provider == "anthropic":
                        # Common Anthropic models
                        model_select.set_options(
                            {
                                "claude-sonnet-4-5": "Claude Sonnet 4.5",
                                "claude-opus-4": "Claude Opus 4",
                                "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet",
                                "claude-3-opus-20240229": "Claude 3 Opus",
                            }
                        )
                    elif provider == "google":
                        # Common Google models
                        model_select.set_options(
                            {
                                "gemini-2.5-pro": "Gemini 2.5 Pro",
                                "gemini-2.0-flash-exp": "Gemini 2.0 Flash",
                                "gemini-1.5-pro": "Gemini 1.5 Pro",
                                "gemini-1.5-flash": "Gemini 1.5 Flash",
                            }
                        )
                    elif provider == "deepseek":
                        # Common DeepSeek models
                        model_select.set_options(
                            {
                                "deepseek-chat": "DeepSeek Chat",
                                "deepseek-coder": "DeepSeek Coder",
                            }
                        )
                    elif provider == "together":
                        # Common Together AI models
                        model_select.set_options(
                            {
                                "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free": "Llama 3.3 70B (Free)",
                                "meta-llama/Llama-3.1-8B-Instruct-Turbo": "Llama 3.1 8B",
                                "mistralai/Mixtral-8x7B-Instruct-v0.1": "Mixtral 8x7B",
                            }
                        )
                    else:
                        model_select.set_options({"": "Select a provider"})

                except Exception as e:
                    model_select.set_options(
                        {"error": f"Error loading models: {str(e)}"}
                    )
                finally:
                    models_loading.set_visibility(False)
                    models_loading_label.set_visibility(False)

            # Load models when provider changes
            async def on_provider_change():
                """Handle provider selection change."""
                provider = provider_select.value
                if provider:
                    await load_models(str(provider))

            provider_select.on("update:model-value", lambda: on_provider_change())

            # Load initial models for default provider (Ollama)
            ui.timer(0.1, lambda: load_models("ollama"), once=True)

            async def send_message():
                """Send message to LLM via agent."""
                message = message_input.value.strip()
                if not message:
                    status_label.text = "Please enter a message"
                    return

                provider = provider_select.value
                model_name = model_select.value

                if not provider:
                    status_label.text = "Please select a provider"
                    return

                if not model_name:
                    status_label.text = "Please select a model"
                    return

                # Update status
                send_button.set_enabled(False)
                status_label.text = f"Sending to {provider}/{model_name}..."
                response_area.content = ""

                try:
                    # Create agent with specific provider and model
                    from draftpilot.agents.orchestrator import (
                        create_agent_with_provider,
                    )

                    # Create agent with the selected provider and model
                    agent = create_agent_with_provider(str(provider), model_name)

                    # Run agent
                    result = await agent.run(message)

                    # Display response
                    response_text = (
                        str(result.output) if hasattr(result, "output") else str(result)
                    )
                    response_area.content = response_text
                    status_label.text = (
                        f"✓ Response received from {provider}/{model_name}"
                    )

                except Exception as e:
                    response_area.content = f"**Error:** {str(e)}"
                    status_label.text = f"✗ Error: {type(e).__name__}"
                    ui.notify(f"Error: {str(e)}", type="negative")

                finally:
                    send_button.set_enabled(True)

            send_button.on_click(send_message)

            # Allow Enter key to send (Ctrl+Enter for newline)
            async def handle_enter():
                """Handle Enter key press to send message."""
                await send_message()

            message_input.on("keydown.enter", handle_enter)


if __name__ in {"__main__", "__mp_main__"}:
    # Use ui.run() when using NiceGUI's app directly
    # This is the standard way to run NiceGUI apps
    ui.run(
        host="0.0.0.0",
        port=8000,
        title="DraftPilot",
        reload=True,  # Auto-reload on file changes
        show=False,  # Don't auto-open browser
    )
