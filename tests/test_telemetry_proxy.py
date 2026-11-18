"""Test the browser telemetry config and the same-origin OTLP proxy."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from draftpilot.api.app import create_app
from draftpilot.core.config import settings

TRACES = "/api/v1/telemetry/v1/traces"
OTLP_JSON = {"content-type": "application/json"}
PAYLOAD = b'{"resourceSpans":[]}'


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Serve the full app (API plus a stub studio build) with no API token."""
    monkeypatch.setattr(settings.api, "token", SecretStr(""))
    (tmp_path / "index.html").write_text("<div id=root></div>")
    return TestClient(create_app(tmp_path))


@pytest.fixture
def collector(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Turn telemetry on and capture what the proxy sends to the OTLP collector."""
    monkeypatch.setattr(settings.otel, "enabled", True)
    monkeypatch.setattr(settings.otel, "exporter_otlp_endpoint", "http://collector:4318/")
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        """Record the forwarded export and accept it."""
        seen.append(request)
        return httpx.Response(200, json={"partialSuccess": {}})

    real: Callable[..., httpx.AsyncClient] = httpx.AsyncClient

    def mocked(**kwargs: Any) -> httpx.AsyncClient:
        """Build the proxy's client over the in-memory collector."""
        return real(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mocked)
    return seen


def test_config_reports_telemetry_off_by_default(client: TestClient) -> None:
    """The studio learns telemetry is off and gets no endpoint or secret."""
    config = client.get("/api/v1/telemetry/config").json()
    assert config["enabled"] is False
    assert config["service_name"].endswith("-browser")
    assert set(config) == {"enabled", "service_name", "service_version", "environment"}


def test_disabled_proxy_is_a_no_op(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """With OTEL__ENABLED=false the proxy accepts and drops exports without calling out."""

    def refuse(**kwargs: Any) -> httpx.AsyncClient:
        """Fail the test if the proxy tries to reach a collector."""
        raise AssertionError("the disabled proxy must not forward")

    monkeypatch.setattr(httpx, "AsyncClient", refuse)
    response = client.post(TRACES, content=PAYLOAD, headers=OTLP_JSON)
    assert response.status_code == 204


def test_enabled_proxy_forwards_to_the_collector(client: TestClient, collector: list[httpx.Request]) -> None:
    """An export reaches `<endpoint>/v1/<signal>` with its body and content type intact."""
    response = client.post(TRACES, content=PAYLOAD, headers=OTLP_JSON)
    assert response.status_code == 200
    assert response.json() == {"partialSuccess": {}}
    metrics = client.post("/api/v1/telemetry/v1/metrics", content=PAYLOAD, headers=OTLP_JSON)
    assert metrics.status_code == 200
    assert [str(request.url) for request in collector] == [
        "http://collector:4318/v1/traces",
        "http://collector:4318/v1/metrics",
    ]
    assert collector[0].content == PAYLOAD
    assert collector[0].headers["content-type"] == "application/json"
    assert "authorization" not in collector[0].headers and "cookie" not in collector[0].headers


def test_proxy_bounds_size_type_and_signal(
    client: TestClient, collector: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Oversized, non-OTLP or unknown-signal posts are refused before reaching the collector."""
    monkeypatch.setattr(settings.otel, "proxy_max_bytes", 8)
    assert client.post(TRACES, content=PAYLOAD, headers=OTLP_JSON).status_code == 413
    assert client.post(TRACES, content=b"{}", headers={"content-type": "text/plain"}).status_code == 415
    assert client.post("/api/v1/telemetry/v1/logs", content=b"{}", headers=OTLP_JSON).status_code == 422
    assert collector == []


def test_proxy_requires_api_auth(
    client: TestClient, collector: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    """With an API token set, exports need it while the public config stays readable."""
    monkeypatch.setattr(settings.api, "token", SecretStr("s3cret-token"))
    assert client.post(TRACES, content=PAYLOAD, headers=OTLP_JSON).status_code == 401
    assert client.get("/api/v1/telemetry/config").status_code == 200
    authed = client.post(TRACES, content=PAYLOAD, headers={**OTLP_JSON, "Authorization": "Bearer s3cret-token"})
    assert authed.status_code == 200
    assert len(collector) == 1


def test_unreachable_collector_is_a_502(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A collector that is down surfaces as a gateway error, not a server crash."""
    monkeypatch.setattr(settings.otel, "enabled", True)
    real = httpx.AsyncClient

    def down(request: httpx.Request) -> httpx.Response:
        """Simulate a refused connection."""
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real(transport=httpx.MockTransport(down), **kwargs))
    assert client.post(TRACES, content=PAYLOAD, headers=OTLP_JSON).status_code == 502
