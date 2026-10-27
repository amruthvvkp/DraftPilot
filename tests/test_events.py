"""Test project change events: publishing, subscribing, and the SSE stream framing."""

import json

import pytest
from _async import run_async

from draftpilot.core import events


class _PubSub:
    """Stand in for a Redis pub/sub connection fed from a list of messages."""

    def __init__(self, messages: list[object]) -> None:
        """Queue messages; ``None`` means an idle poll."""
        self.messages = messages
        self.closed = False

    async def subscribe(self, _channel: str) -> None:
        """Accept the subscription."""

    async def unsubscribe(self, _channel: str) -> None:
        """Accept the unsubscription."""

    async def aclose(self) -> None:
        """Record that the connection closed."""
        self.closed = True

    async def get_message(self, ignore_subscribe_messages: bool, timeout: float) -> object:
        """Return the next queued message."""
        return self.messages.pop(0) if self.messages else None


class _Redis:
    """Capture publishes and hand out one pub/sub connection."""

    def __init__(self, pubsub: _PubSub) -> None:
        """Remember the pub/sub stand-in."""
        self.published: list[tuple[str, str]] = []
        self._pubsub = pubsub

    async def publish(self, channel: str, message: str) -> None:
        """Capture one published message."""
        self.published.append((channel, message))

    def pubsub(self) -> _PubSub:
        """Return the pub/sub stand-in."""
        return self._pubsub


def test_publish_tags_events_with_the_originating_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Published events carry the project, kind, data, and the request's client id."""
    redis = _Redis(_PubSub([]))
    monkeypatch.setattr(events, "get_redis", lambda: redis)

    async def request() -> None:
        """Bind the client and publish within one task, as a request does."""
        events.bind_client("tab-123")
        await events.publish(9, "scene.changed", {"scene_id": 7})

    run_async(request())
    channel, raw = redis.published[0]
    assert channel == "draftpilot:events:project:9"
    event = json.loads(raw)
    assert (event["kind"], event["client"], event["data"]) == ("scene.changed", "tab-123", {"scene_id": 7})


def test_publish_never_raises_when_redis_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live sync is best-effort; a Redis outage must not fail the write path."""

    class Broken:
        """Fail every publish."""

        async def publish(self, *_args: object) -> None:
            """Raise like an unreachable Redis."""
            raise ConnectionError("down")

    monkeypatch.setattr(events, "get_redis", lambda: Broken())
    run_async(events.publish(9, "scene.changed"))


def test_subscribe_yields_events_and_heartbeats(monkeypatch: pytest.MonkeyPatch) -> None:
    """Subscribers get decoded events, ``None`` heartbeats, and skip malformed payloads."""
    event = events.build_event(9, "proposal.changed", {"proposal_id": 1}, None)
    pubsub = _PubSub([{"data": json.dumps(event)}, None, {"data": "not json"}, {"data": json.dumps(event)}])
    monkeypatch.setattr(events, "get_redis", lambda: _Redis(pubsub))

    async def collect() -> list[object]:
        """Read three items from the subscription."""
        received: list[object] = []
        stream = events.subscribe(9, heartbeat_seconds=0)
        async for item in stream:
            received.append(item)
            if len(received) == 3:
                break
        await stream.aclose()
        return received

    received = run_async(collect())
    assert received == [event, None, event]
    assert pubsub.closed
