"""Browser telemetry: the public config the studio reads and a same-origin OTLP proxy.

The studio never talks to a collector directly and never holds an exporter credential. It posts
OTLP/HTTP to ``/api/v1/telemetry/v1/{traces,metrics}`` on its own origin, behind the API auth,
and this proxy forwards the bounded payload to ``OTEL__EXPORTER_OTLP_ENDPOINT``.
"""

from typing import Literal

import httpx
import logfire
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from draftpilot.core.config import settings

# The config is public, like /auth/status, so the SPA can start tracing before sign-in.
public_router = APIRouter(prefix="/telemetry", tags=["telemetry"])
router = APIRouter(prefix="/telemetry", tags=["telemetry"])

PROXY_PATH = "/api/v1/telemetry/v1/"
_FORWARDED_HEADERS = ("content-type", "content-encoding")
_CONTENT_TYPES = ("application/json", "application/x-protobuf")


class TelemetryConfig(BaseModel):
    """Tell the browser whether to load the telemetry SDK, and how to label its spans."""

    enabled: bool
    service_name: str
    service_version: str
    environment: str


@public_router.get("/config", response_model=TelemetryConfig)
async def telemetry_config() -> TelemetryConfig:
    """Return the browser telemetry switch and resource labels (never an exporter secret)."""
    return TelemetryConfig(
        enabled=settings.otel.enabled,
        service_name=f"{settings.metadata.name}-browser",
        service_version=settings.metadata.version,
        environment=settings.otel.environment,
    )


async def _bounded_body(request: Request, limit: int) -> bytes:
    """Read the request body, rejecting it with 413 once it passes ``limit`` bytes."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "OTLP payload too large")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "OTLP payload too large")
    return bytes(body)


@router.post("/v1/{signal}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def forward_otlp(signal: Literal["traces", "metrics"], request: Request) -> Response:
    """Forward one browser OTLP/HTTP export to the configured collector; a no-op when telemetry is off."""
    if not settings.otel.enabled:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in _CONTENT_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "OTLP must be JSON or protobuf")
    body = await _bounded_body(request, settings.otel.proxy_max_bytes)
    headers = {name: value for name in _FORWARDED_HEADERS if (value := request.headers.get(name))}
    target = f"{settings.otel.exporter_otlp_endpoint.rstrip('/')}/v1/{signal}"
    # The export must not trace itself, or every batch would produce another one.
    with logfire.suppress_instrumentation():
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                upstream = await client.post(target, content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "OTLP collector unreachable") from exc
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )
