import os

import logfire

from draftpilot.core.config import settings


def setup(ui: bool = False, mcp: bool = False) -> None:
    if not settings.otel.enabled:
        logfire.info("OTEL is disabled; skipping telemetry setup")
        return

    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = settings.otel.exporter_otlp_endpoint
    # Configure Logfire
    logfire.configure(
        service_name=f"{settings.metadata.name}-ui"
        if ui
        else f"{settings.metadata.name}-mcp"
        if mcp
        else settings.metadata.name,
        service_version=settings.metadata.version,
        send_to_logfire=False,
        distributed_tracing=True,
    )

    # Instrument Logfire with pydantic, and system metrics
    logfire.instrument_pydantic()
    logfire.instrument_system_metrics()

    # Configure UI telemetry if enabled
    if ui:
        import flet.fastapi as flet_fastapi

        app = flet_fastapi.FastAPI()

        logfire.instrument_fastapi(app)
        logfire.instrument_httpx(capture_request_body=True, capture_response_body=True)
        logfire.instrument_pydantic_ai()

    # Configure MCP telemetry if enabled
    if mcp:
        pass
        # https://github.com/timvw/fastmcp-otel-langfuse/blob/main/README.md
