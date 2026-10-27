"""Project change events over Redis pub/sub, streamed to open studios as Server-Sent Events.

Every process that changes a project (web, worker, MCP) publishes here, so an edit made by an
agent or an external MCP client appears live in the writer's open workspace. Events carry the
originating browser tab id so a tab can ignore echoes of its own edits.
"""

import json
from collections.abc import AsyncIterator
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

import logfire

from draftpilot.core.cache import get_redis

CLIENT_HEADER = "X-DraftPilot-Client"
_current_client: ContextVar[str | None] = ContextVar("draftpilot_client", default=None)


def bind_client(client_id: str | None) -> None:
    """Record the browser tab (or agent) that issued the current request."""
    _current_client.set(client_id[:100] if client_id else None)


def channel(project_id: int) -> str:
    """Return the pub/sub channel carrying one project's change events."""
    return f"draftpilot:events:project:{project_id}"


def build_event(project_id: int, kind: str, data: dict[str, Any], client: str | None) -> dict[str, Any]:
    """Build the JSON event envelope published for one committed change."""
    return {
        "kind": kind,
        "project_id": project_id,
        "client": client,
        "at": datetime.now(UTC).isoformat(),
        "data": data,
    }


async def publish(project_id: int, kind: str, data: dict[str, Any] | None = None) -> None:
    """Publish a committed change; delivery is best-effort and never fails the caller."""
    event = build_event(project_id, kind, data or {}, _current_client.get())
    try:
        await get_redis().publish(channel(project_id), json.dumps(event, default=str))
    except Exception as exc:  # noqa: BLE001 - live sync must never break the write path
        logfire.warning("Project event publish skipped: {exc}", exc=str(exc))


async def subscribe(project_id: int, heartbeat_seconds: float = 15.0) -> AsyncIterator[dict[str, Any] | None]:
    """Yield a project's events as they arrive, and ``None`` as a heartbeat when idle."""
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(channel(project_id))
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=heartbeat_seconds)
            if message is None:
                yield None
                continue
            try:
                yield json.loads(message["data"])
            except (TypeError, ValueError):
                continue
    finally:
        await pubsub.unsubscribe(channel(project_id))
        await pubsub.aclose()
