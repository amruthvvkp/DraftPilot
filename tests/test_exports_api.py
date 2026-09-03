"""Test safe screenplay import and export HTTP boundaries."""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from draftpilot.api.exports import router
from draftpilot.core.db import async_get_db
from draftpilot.models import Project, Screenplay, ScreenplayCreate


class _Session:
    """Stand in for the database session in import tests."""


def test_fountain_import_creates_a_new_screenplay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import valid Fountain without mutating the source screenplay."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session, None]:
        """Yield an isolated database marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    project = Project(id=9, title="Story")
    source = Screenplay(id=2, project_id=9, title="Draft", format="feature")
    imported = Screenplay(id=3, project_id=9, title="Draft (Imported)", format="feature")
    created: list[ScreenplayCreate] = []
    saved: list[int] = []

    async def get(_session: _Session, item_id: int) -> Project | Screenplay | None:
        """Return the project or source screenplay fixture."""
        return project if item_id == 9 else source if item_id == 2 else None

    async def create(_session: _Session, data: ScreenplayCreate) -> Screenplay:
        """Capture the new screenplay request."""
        created.append(data)
        return imported

    async def save(_session: _Session, screenplay_id: int, _document: object) -> None:
        """Capture canonical document persistence."""
        saved.append(screenplay_id)

    monkeypatch.setattr("draftpilot.api.exports.projects_crud.get", get)
    monkeypatch.setattr("draftpilot.api.exports.screenplays_crud.get", get)
    monkeypatch.setattr("draftpilot.api.exports.screenplays_crud.create", create)
    monkeypatch.setattr("draftpilot.api.exports.save_screenplay_doc", save)
    response = TestClient(app).post(
        "/api/v1/projects/9/screenplays/2/imports/fountain",
        content="INT. HOUSE - DAY\n\nA quiet room.",
    )
    assert response.status_code == 201
    assert response.json()["id"] == 3
    assert created[0].title == "Draft (Imported)"
    assert saved == [3]


def test_import_rejects_unsupported_format() -> None:
    """Reject unknown import formats at the HTTP boundary."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    response = TestClient(app).post(
        "/api/v1/projects/9/screenplays/2/imports/pdf", content=b"not a screenplay"
    )
    assert response.status_code == 422
