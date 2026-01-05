"""Logfire OTEL integration for DraftPilot."""

import os
from typing import TYPE_CHECKING

import logfire

if TYPE_CHECKING:
    from logfire import Logfire

from draftpilot.core.config import settings

__all__ = ["configure_logfire"]


def configure_logfire(app=None) -> "Logfire | None":
    """Configure and initialize Logfire with OTEL exporter.

    Sets up Logfire with OTEL configuration to send traces to Grafana LGTM
    collector. Enables auto-instrumentation for FastAPI if app is provided.

    :param app: Optional FastAPI app instance for instrumentation.
               If provided, will instrument this app. If None, only configures Logfire.
    :return: Logfire instance if enabled, None otherwise.
    """
    if not settings.logfire.enabled:
        return None

    # Skip instrumentation during testing (pytest sets this env var)
    is_testing = os.environ.get("PYTEST_CURRENT_TEST") is not None

    # Set OTEL endpoint via environment variable (Logfire reads this)
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = settings.logfire.otel_endpoint

    # Configure Logfire
    logfire.configure(
        service_name=settings.logfire.service_name,
        send_to_logfire=False,  # We're sending to our own OTEL collector
    )

    # Auto-instrument FastAPI if app is provided and not in test mode
    # This should be called with the main FastAPI app that NiceGUI is mounted on
    if app is not None and not is_testing:
        try:
            logfire.instrument_fastapi(app)
        except Exception:
            # Silently fail during testing or if instrumentation is not available
            if not is_testing:
                raise

    return logfire  # type: ignore[return-value]
