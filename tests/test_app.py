"""Test the FastAPI application factory that replaced the NiceGUI host."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from draftpilot.api.app import _spa_file, create_app


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """Build a minimal React studio output directory."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log('studio')")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("do not serve")
    return tmp_path


def test_health_and_api_are_served(dist: Path) -> None:
    """The factory exposes health and the versioned API without a NiceGUI host."""
    client = TestClient(create_app(dist))
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/v1/agents/roles").status_code == 200


def test_spa_serves_assets_files_and_client_routes(dist: Path) -> None:
    """Built files are served directly; unknown client routes get the SPA shell."""
    client = TestClient(create_app(dist))
    assert "studio" in client.get("/assets/app.js").text
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/projects/9/studio").text == "<div id=root></div>"


def test_unknown_api_paths_are_not_swallowed_by_the_spa(dist: Path) -> None:
    """A mistyped API path is a 404, not the HTML shell."""
    assert TestClient(create_app(dist)).get("/api/v1/nope").status_code == 404


def test_spa_fallback_never_escapes_the_build_directory(dist: Path) -> None:
    """Traversal outside the build directory resolves to the SPA shell."""
    assert _spa_file(dist, "../secret.txt") == dist.resolve() / "index.html"
    assert _spa_file(dist, "favicon.svg") == dist.resolve() / "favicon.svg"


def test_app_starts_without_a_frontend_build(tmp_path: Path) -> None:
    """The API still serves when the React build is missing."""
    client = TestClient(create_app(tmp_path / "missing"))
    assert client.get("/health").status_code == 200
    assert client.get("/projects").status_code == 404
