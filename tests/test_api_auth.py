"""Test single-user REST API authentication."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from draftpilot.api import router
from draftpilot.core import api_auth
from draftpilot.core.config import settings

ROLES = "/api/v1/agents/roles"


def _client() -> TestClient:
    """Build a client over the full versioned API router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def token(monkeypatch: pytest.MonkeyPatch) -> str:
    """Configure an API token for the duration of one test."""
    monkeypatch.setattr(settings.api, "token", SecretStr("s3cret-token"))
    return "s3cret-token"


def test_api_is_open_when_no_token_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """A loopback development install without a token needs no credentials."""
    monkeypatch.setattr(settings.api, "token", SecretStr(""))
    client = _client()
    assert client.get(ROLES).status_code == 200
    assert client.get("/api/v1/auth/status").json() == {"auth_required": False, "authenticated": True}


def test_configured_token_protects_every_api_route(token: str) -> None:
    """Protected routes reject missing or wrong credentials and accept the bearer token."""
    client = _client()
    assert client.get(ROLES).status_code == 401
    assert client.get(ROLES, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get(ROLES, headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/api/v1/auth/status").json() == {"auth_required": True, "authenticated": False}


def test_browser_session_cookie_signs_in_and_out(token: str) -> None:
    """Submitting the token once sets an HttpOnly session used by later requests."""
    client = _client()
    assert client.post("/api/v1/auth/session", json={"token": "wrong"}).status_code == 401
    signed_in = client.post("/api/v1/auth/session", json={"token": token})
    assert signed_in.status_code == 200
    assert "httponly" in signed_in.headers["set-cookie"].lower()
    assert client.get(ROLES).status_code == 200
    assert client.delete("/api/v1/auth/session").status_code == 204
    client.cookies.clear()
    assert client.get(ROLES).status_code == 401


def test_session_cookie_rejects_tampering_expiry_and_token_rotation(
    token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forged, expired, or pre-rotation sessions are not accepted."""
    cookie = api_auth.issue_session(now=1_000_000)
    assert api_auth.session_valid(cookie, now=1_000_100)
    issued, _, signature = cookie.partition(".")
    assert not api_auth.session_valid(f"{int(issued) + 1}.{signature}", now=1_000_100)
    assert not api_auth.session_valid("garbage", now=1_000_100)
    assert not api_auth.session_valid(cookie, now=1_000_000 + settings.api.session_max_age_seconds + 1)
    monkeypatch.setattr(settings.api, "token", SecretStr("rotated-token"))
    assert not api_auth.session_valid(cookie, now=1_000_100)
