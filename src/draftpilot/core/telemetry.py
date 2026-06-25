"""Logfire-based telemetry: traces, metrics, and logs over OTLP.

Logfire is the single instrumentation + logging backend for DraftPilot. It
exports to the OTLP endpoint configured in settings (Grafana LGTM in compose)
and is never sent to the Logfire cloud. Call :func:`setup` once per process,
selecting the role so the service name and instrumentation match.
"""

import os

import logfire

from draftpilot.core.config import settings


def _service_name(ui: bool, mcp: bool, worker: bool) -> str:
    """Return the OTLP service name for the running process role."""
    if ui:
        return f"{settings.metadata.name}-ui"
    if mcp:
        return f"{settings.metadata.name}-mcp"
    if worker:
        return f"{settings.metadata.name}-worker"
    return settings.metadata.name


def setup(ui: bool = False, mcp: bool = False, worker: bool = False) -> None:
    """Configure Logfire and instrument the libraries used by this process."""
    if not settings.otel.enabled:
        logfire.info("OTEL is disabled; skipping telemetry setup")
        return

    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = settings.otel.exporter_otlp_endpoint
    logfire.configure(
        service_name=_service_name(ui, mcp, worker),
        service_version=settings.metadata.version,
        send_to_logfire=False,
        distributed_tracing=True,
    )

    # Common instrumentation for every process.
    logfire.instrument_pydantic()
    logfire.instrument_system_metrics()

    # Data-plane instrumentation shared by the web and worker processes.
    if ui or worker:
        logfire.instrument_asyncpg()
        logfire.instrument_redis()
        logfire.instrument_httpx(capture_request_body=True, capture_response_body=True)
        logfire.instrument_pydantic_ai()

    # NiceGUI runs on FastAPI: ``from nicegui import app`` is the FastAPI app.
    if ui:
        from nicegui import app as nicegui_app

        logfire.instrument_fastapi(nicegui_app)

    # MCP telemetry is handled by FastMCP's own instrumentation hooks.
    if mcp:
        pass
