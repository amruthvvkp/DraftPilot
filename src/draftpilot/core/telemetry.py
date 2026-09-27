"""Logfire-based telemetry: traces, metrics, and logs over OTLP.

Logfire is the single instrumentation + logging backend for DraftPilot. It
exports to the OTLP endpoint configured in settings (the bundled Langfuse in compose)
and is never sent to the Logfire cloud. Call :func:`setup` once per process,
selecting the role so the service name and instrumentation match.
"""

import os
from typing import TYPE_CHECKING

import logfire

from draftpilot.core.config import settings

if TYPE_CHECKING:
    from fastapi import FastAPI


def _service_name(web: bool, mcp: bool, worker: bool) -> str:
    """Return the OTLP service name for the running process role."""
    if web:
        return f"{settings.metadata.name}-web"
    if mcp:
        return f"{settings.metadata.name}-mcp"
    if worker:
        return f"{settings.metadata.name}-worker"
    return settings.metadata.name


_configured_role: str | None = None


def setup(web: bool = False, mcp: bool = False, worker: bool = False) -> None:
    """Configure Logfire once per process; the first role to call wins.

    The web and worker processes load the MCP server in-process for in-app agents, and its
    module-level ``setup(mcp=True)`` must not relabel their telemetry.
    """
    global _configured_role
    if _configured_role is not None:
        return
    _configured_role = _service_name(web, mcp, worker)
    if not settings.otel.enabled:
        logfire.info("OTEL is disabled; skipping telemetry setup")
        return

    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = settings.otel.exporter_otlp_endpoint
    logfire.configure(
        service_name=_service_name(web, mcp, worker),
        service_version=settings.metadata.version,
        send_to_logfire=False,
        distributed_tracing=True,
    )

    # Common instrumentation for every process.
    logfire.instrument_pydantic()
    logfire.instrument_system_metrics()

    # Data-plane instrumentation shared by the web and worker processes.
    if web or worker:
        logfire.instrument_asyncpg()
        logfire.instrument_redis()
        logfire.instrument_httpx(capture_request_body=True, capture_response_body=True)
        logfire.instrument_pydantic_ai()

    if mcp:
        instrument_mcp()


def instrument_app(app: "FastAPI") -> None:
    """Instrument the web process's FastAPI app when telemetry is enabled."""
    if settings.otel.enabled:
        logfire.instrument_fastapi(app)


def instrument_mcp() -> None:
    """Instrument MCP client/server sessions where the installed Logfire supports it.

    MCP SDK 2 and FastMCP 4 emit OpenTelemetry client and server spans and propagate
    ``traceparent`` natively, so traces already flow through Logfire's tracer provider.
    ``logfire.instrument_mcp`` targets the MCP 1.x session API; on Logfire releases that
    predate MCP 2 support it fails at import, so it is attempted and skipped cleanly.
    """
    try:
        logfire.instrument_mcp()
    except (ImportError, AttributeError) as exc:
        logfire.info("Using native MCP OpenTelemetry spans ({reason})", reason=type(exc).__name__)
