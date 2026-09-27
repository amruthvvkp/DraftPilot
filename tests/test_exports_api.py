"""Test safe screenplay import and export HTTP boundaries."""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.exports import router
from draftpilot.core.db import async_get_db
from draftpilot.core.screenplay.adapters.pdf import parse_pdf
from draftpilot.core.screenplay.schema import ScreenplayDoc
from draftpilot.models import Project, Screenplay, ScreenplayCreate


class _Session:
    """Stand in for the database session in import tests."""


def test_benchmark_manifest_is_project_scoped_and_metadata_bearing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Build a benchmark manifest without exposing or mutating database state."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session]:
        """Yield an isolated database marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    project = Project(id=9, title="Story", primary_language="Hindi", languages=["English"])
    screenplay = Screenplay(
        id=2,
        project_id=9,
        title="Draft",
        format="feature",
        source_sha256="a" * 64,
    )

    async def get(_session: _Session, item_id: int) -> Project | Screenplay | None:
        """Return only the scoped project and screenplay fixtures."""
        return project if item_id == 9 else screenplay if item_id == 2 else None

    async def load(_session: _Session, _screenplay_id: int) -> ScreenplayDoc:
        """Return one canonical fixture document."""
        return ScreenplayDoc.model_validate({"acts": [{"scenes": [{"heading": "INT. HOUSE - DAY"}]}]})

    monkeypatch.setattr("draftpilot.api.exports.projects_crud.get", get)
    monkeypatch.setattr("draftpilot.api.exports.screenplays_crud.get", get)
    monkeypatch.setattr("draftpilot.api.exports.load_screenplay_doc", load)
    response = TestClient(app).get("/api/v1/projects/9/screenplays/2/benchmark-manifest")

    assert response.status_code == 200
    assert response.json()["track"] == "redevelopment"
    assert response.json()["primary_language"] == "Hindi"
    assert response.json()["translation_languages"] == ["English"]
    assert response.json()["source_sha256"] == "a" * 64

    control_response = TestClient(app).get(
        "/api/v1/projects/9/screenplays/2/benchmark-manifest?track=import_compare"
    )
    assert control_response.status_code == 200
    assert control_response.json()["track"] == "import_compare"
    assert control_response.json()["label"].startswith("import_compare-")

    invalid_response = TestClient(app).get(
        "/api/v1/projects/9/screenplays/2/benchmark-manifest?track=unknown"
    )
    assert invalid_response.status_code == 422


def test_fountain_import_creates_a_new_screenplay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import valid Fountain without mutating the source screenplay."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session]:
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
    assert created[0].source_sha256
    assert saved == [3]


def test_import_rejects_malformed_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject malformed PDF content at the HTTP boundary."""
    app = FastAPI()
    async def session() -> AsyncGenerator[_Session]:
        """Yield an isolated database marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    project = Project(id=9, title="Story")
    source = Screenplay(id=2, project_id=9, title="Draft", format="feature")

    async def get(_session: _Session, item_id: int) -> Project | Screenplay | None:
        """Return the project and source screenplay fixture."""
        return project if item_id == 9 else source if item_id == 2 else None

    monkeypatch.setattr("draftpilot.api.exports.projects_crud.get", get)
    monkeypatch.setattr("draftpilot.api.exports.screenplays_crud.get", get)
    response = TestClient(app).post(
        "/api/v1/projects/9/screenplays/2/imports/pdf", content=b"not a screenplay"
    )
    assert response.status_code == 422


def test_pdf_parser_recovers_scene_and_dialogue() -> None:
    """Recover conservative scene semantics from a rendered PDF."""
    from draftpilot.core.screenplay.pdf import render_pdf
    from draftpilot.core.screenplay.schema import (
        ActDoc,
        BlockDoc,
        SceneDoc,
        ScreenplayDoc,
    )
    from draftpilot.models.enums import BlockType

    document = ScreenplayDoc(
        acts=[
            ActDoc(
                scenes=[
                    SceneDoc(
                        heading="INT. HOUSE - DAY",
                        blocks=[
                            BlockDoc(element_type=BlockType.ACTION, text="A quiet room."),
                            BlockDoc(element_type=BlockType.CHARACTER, text="MAYA"),
                            BlockDoc(element_type=BlockType.DIALOGUE, text="Hello."),
                        ],
                    )
                ]
            )
        ]
    )
    recovered = parse_pdf(render_pdf(document))
    assert recovered.acts[0].scenes[0].heading == "INT. HOUSE - DAY"
    assert [block.element_type for block in recovered.acts[0].scenes[0].blocks][-2:] == [BlockType.CHARACTER, BlockType.DIALOGUE]


def test_html_export_returns_safe_print_document(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return canonical screenplay data as escaped HTML without mutation."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session]:
        """Yield an isolated database marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    project = Project(id=9, title="Story")
    screenplay = Screenplay(id=2, project_id=9, title="Draft", format="feature")

    async def get(_session: _Session, item_id: int) -> Project | Screenplay | None:
        """Return the export fixtures."""
        return project if item_id == 9 else screenplay if item_id == 2 else None

    async def load(_session: _Session, _screenplay_id: int) -> ScreenplayDoc:
        """Return a document containing markup-like title text."""
        return ScreenplayDoc(title_page={"Title": "<Unsafe>"})

    monkeypatch.setattr("draftpilot.api.exports.projects_crud.get", get)
    monkeypatch.setattr("draftpilot.api.exports.screenplays_crud.get", get)
    monkeypatch.setattr("draftpilot.api.exports.load_screenplay_doc", load)
    response = TestClient(app).get("/api/v1/projects/9/screenplays/2/exports/html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "&lt;Unsafe&gt;" in response.text
    assert response.headers["content-disposition"].endswith('filename="Draft.html"')


BIG_FISH = Path(__file__).parent / "test_screenplays"


@pytest.mark.parametrize(
    ("file_format", "filename"),
    [("fountain", "Big-Fish.fountain"), ("fdx", "Big-Fish.xml"), ("pdf", "Big-Fish.pdf")],
)
def test_real_screenplay_imports_over_http(
    monkeypatch: pytest.MonkeyPatch, file_format: str, filename: str
) -> None:
    """Import the full Big Fish screenplay in each supported format over HTTP."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session]:
        """Yield an isolated database marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    project = Project(id=9, title="Story")
    source = Screenplay(id=2, project_id=9, title="Draft", format="feature")
    documents: list[ScreenplayDoc] = []

    async def get(_session: _Session, item_id: int) -> Project | Screenplay | None:
        """Return the project or source screenplay fixture."""
        return project if item_id == 9 else source if item_id == 2 else None

    async def create(_session: _Session, data: ScreenplayCreate) -> Screenplay:
        """Return the imported screenplay row."""
        return Screenplay(id=3, project_id=9, title=data.title, format="feature")

    async def save(_session: _Session, _screenplay_id: int, document: ScreenplayDoc) -> None:
        """Capture the parsed canonical document."""
        documents.append(document)

    monkeypatch.setattr("draftpilot.api.exports.projects_crud.get", get)
    monkeypatch.setattr("draftpilot.api.exports.screenplays_crud.get", get)
    monkeypatch.setattr("draftpilot.api.exports.screenplays_crud.create", create)
    monkeypatch.setattr("draftpilot.api.exports.save_screenplay_doc", save)
    response = TestClient(app).post(
        f"/api/v1/projects/9/screenplays/2/imports/{file_format}",
        content=(BIG_FISH / filename).read_bytes(),
    )
    assert response.status_code == 201, response.text
    scenes = [scene for act in documents[0].acts for scene in act.scenes]
    assert len(scenes) >= 180
