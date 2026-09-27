"""Test the FastAPI application factory: the versioned API plus the React studio build."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from draftpilot.api.app import IMMUTABLE, create_app
from draftpilot.core.config import settings

HTML = {"accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
SHELL = "<div id=root></div>"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """Build a minimal React studio output directory."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(SHELL)
    (tmp_path / "assets" / "app.js").write_text("console.log('studio')")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("do not serve")
    return tmp_path


def test_health_and_api_are_served(dist: Path) -> None:
    """The factory exposes health and the versioned API."""
    client = TestClient(create_app(dist))
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/v1/agents/roles").status_code == 200


def test_spa_serves_assets_files_and_deep_links(dist: Path) -> None:
    """Built files are served directly; a browser deep link gets the SPA shell."""
    client = TestClient(create_app(dist))
    assert "studio" in client.get("/assets/app.js").text
    assert client.get("/favicon.svg").text == "<svg/>"
    deep_link = client.get("/projects/9/studio", headers=HTML)
    assert deep_link.status_code == 200
    assert deep_link.text == SHELL


def test_assets_are_immutable_and_the_shell_revalidates(dist: Path) -> None:
    """Hashed assets cache forever; ``index.html`` is revalidated on every load."""
    client = TestClient(create_app(dist))
    assert client.get("/assets/app.js").headers["cache-control"] == IMMUTABLE
    assert client.get("/", headers=HTML).headers["cache-control"] == "no-cache"
    assert client.get("/projects/9", headers=HTML).headers["cache-control"] == "no-cache"


def test_missing_asset_is_a_404_not_the_shell(dist: Path) -> None:
    """A stale or mistyped asset URL fails loudly instead of returning HTML."""
    missing = TestClient(create_app(dist)).get("/assets/gone.js")
    assert missing.status_code == 404
    assert "cache-control" not in missing.headers


def test_unknown_api_paths_are_not_shadowed_by_the_spa(dist: Path) -> None:
    """A mistyped API path is a JSON 404, even when a browser asks for HTML."""
    client = TestClient(create_app(dist))
    for headers in ({}, HTML):
        response = client.get("/api/v1/nope", headers=headers)
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"


def test_post_to_an_unknown_path_is_a_404(dist: Path) -> None:
    """The SPA fallback only answers reads."""
    assert TestClient(create_app(dist)).post("/projects/9", headers=HTML).status_code == 404


def test_auth_guards_the_api_and_sse_but_not_the_shell(
    dist: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a token set, the SSE stream is answered by the API; the shell and token prompt still load."""
    monkeypatch.setattr(settings.api, "token", SecretStr("s3cret-token"))
    client = TestClient(create_app(dist))
    for accept in ("text/event-stream", HTML["accept"]):
        sse = client.get("/api/v1/projects/1/events", headers={"accept": accept})
        assert sse.status_code == 401
        assert sse.headers["content-type"] == "application/json"
    assert client.get("/projects/1", headers=HTML).text == SHELL
    assert "studio" in client.get("/assets/app.js").text


def test_spa_never_escapes_the_build_directory(dist: Path) -> None:
    """Traversal outside the build directory never serves the file."""
    client = TestClient(create_app(dist))
    for path in ("/../secret.txt", "/%2e%2e/secret.txt"):
        assert "do not serve" not in client.get(path, headers=HTML).text


def test_app_starts_without_a_frontend_build(tmp_path: Path) -> None:
    """The API still serves when the React build is missing and not required."""
    client = TestClient(create_app(tmp_path / "missing"))
    assert client.get("/health").status_code == 200
    assert client.get("/projects", headers=HTML).status_code == 404


def test_required_frontend_fails_fast_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The production image (``WEB__REQUIRE_FRONTEND=true``) refuses to start without a build."""
    monkeypatch.setattr(settings.web, "require_frontend", True)
    with pytest.raises(RuntimeError, match="does not exist"):
        create_app(tmp_path / "missing")
