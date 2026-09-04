"""Test the versioned project REST boundary without a live database."""

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.projects import router
from draftpilot.api.runs import router as runs_router
from draftpilot.core.db import async_get_db
from draftpilot.models import (
    Act,
    Block,
    BlockType,
    DialogueTranslation,
    Project,
    ProjectReference,
    Scene,
    Screenplay,
    WorkflowRun,
)


class _Session:
    """Stand in for an async SQLModel session in API tests."""

    def add(self, _value: object) -> None:
        """Accept a model mutation in the isolated session."""

    async def commit(self) -> None:
        """Commit the isolated model mutation."""

    async def refresh(self, _value: object) -> None:
        """Refresh the isolated model mutation."""


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build an isolated API client with a mocked database dependency."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session, None]:
        """Yield an in-memory session marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    app.include_router(runs_router, prefix="/api/v1")
    return TestClient(app)


def test_empty_project_list_is_json(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Return an empty project collection without touching Postgres."""
    async def list_all(_session: _Session) -> list[Project]:
        """Return no projects for the isolated test database."""
        return []

    monkeypatch.setattr("draftpilot.api.projects.projects_crud.list_all", list_all)
    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    assert response.json() == []


def test_create_project_persists_typed_references(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass typed references through the request and return them in the response."""
    project = Project(id=9, title="A multilingual story", primary_language="Hindi")
    refresh = AsyncMock()

    async def create_with_references(_session: _Session, data: object, references: list[object]) -> Project:
        """Return the fixture project after receiving the normalized request."""
        assert getattr(data, "primary_language") == "Hindi"
        assert len(references) == 1
        assert getattr(references[0], "label") == "Pather Panchali"
        return project

    async def list_for_project(_session: _Session, _project_id: int) -> list[object]:
        """Return the reference created by the mocked persistence layer."""
        return [
            ProjectReference(
                id=11,
                project_id=9,
                kind="film",
                label="Pather Panchali",
                note="Texture",
                version=1,
            )
        ]

    monkeypatch.setattr(
        "draftpilot.api.projects.projects_crud.create_with_references", create_with_references
    )
    monkeypatch.setattr(
        "draftpilot.api.projects.references_crud.list_for_project", list_for_project
    )
    monkeypatch.setattr("draftpilot.api.projects._enqueue_rag_index", refresh)
    response = client.post(
        "/api/v1/projects",
        json={
            "title": project.title,
            "primary_language": "Hindi",
            "genres": ["Drama"],
            "languages": ["Bengali"],
            "references": [{"kind": "film", "label": "Pather Panchali"}],
        },
    )
    assert response.status_code == 201
    assert response.json()["primary_language"] == "Hindi"
    assert refresh.await_count == 2
    assert refresh.await_args_list[0].args[:3] == (9, "project:9", "project")
    assert refresh.await_args_list[1].args[:3] == (9, "reference:11", "reference")


def test_create_project_rejects_missing_title(client: TestClient) -> None:
    """Reject an invalid project brief before any persistence call."""
    response = client.post("/api/v1/projects", json={"genres": [], "languages": []})
    assert response.status_code == 422


def test_create_project_rejects_primary_language_translation_target(client: TestClient) -> None:
    """Reject a project that lists its screenplay language as a translation target."""
    response = client.post(
        "/api/v1/projects",
        json={
            "title": "Language-safe story",
            "primary_language": " Hindi ",
            "genres": [],
            "languages": ["Bengali", "hindi"],
        },
    )
    assert response.status_code == 422


def test_project_artwork_upload_is_bounded_and_persisted_locally(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Persist a validated image in the configured local artwork volume."""
    project = Project(id=9, title="Artwork story", version=4)

    async def get_project(_session: _Session, _project_id: int) -> Project:
        """Return the isolated artwork project."""
        return project

    monkeypatch.setattr("draftpilot.api.projects.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.projects.settings.backup", type("Backup", (), {"root": tmp_path})())
    response = client.post(
        "/api/v1/projects/9/artwork",
        files={"artwork": ("cover.png", b"\x89PNG\r\n\x1a\ncover", "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["artwork_url"].startswith("/artwork/")
    assert project.artwork_path is not None
    assert (tmp_path / project.artwork_path).read_bytes() == b"\x89PNG\r\n\x1a\ncover"


def test_project_artwork_upload_rejects_mismatched_signature(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject an image MIME type whose bytes do not match its declared format."""
    monkeypatch.setattr(
        "draftpilot.api.projects.projects_crud.get",
        AsyncMock(return_value=Project(id=9, title="Artwork story")),
    )
    response = client.post(
        "/api/v1/projects/9/artwork",
        files={"artwork": ("cover.png", b"not-an-image", "image/png")},
    )
    assert response.status_code == 422


def test_scene_update_requires_matching_if_match(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject stale scene edits without calling the persistence layer."""
    scene = Scene(id=7, act_id=4, heading="INT. HOUSE - DAY", version=3)
    act = Act(id=4, screenplay_id=2, position=0)
    screenplay = Screenplay(id=2, project_id=9, title="Story")

    async def get_scene(_session: _Session, _scene_id: int) -> Scene:
        """Return the versioned scene fixture."""
        return scene

    async def get_act(_session: _Session, _act_id: int) -> Act:
        """Return the owning act fixture."""
        return act

    async def get_screenplay(_session: _Session, _screenplay_id: int) -> Screenplay:
        """Return the owning screenplay fixture."""
        return screenplay

    monkeypatch.setattr("draftpilot.api.projects.scenes_crud.get", get_scene)
    monkeypatch.setattr("draftpilot.api.projects.acts_crud.get", get_act)
    monkeypatch.setattr("draftpilot.api.projects.screenplays_crud.get", get_screenplay)
    response = client.patch(
        "/api/v1/projects/9/scenes/7",
        headers={"If-Match": "2"},
        json={"body": "A changed room."},
    )
    assert response.status_code == 409


def test_scene_creation_requires_the_requested_screenplay_and_act(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Create a scene only when both screenplay and act belong to the project."""
    project = Project(id=9, title="Story")
    screenplay = Screenplay(id=2, project_id=9, title="Story")
    act = Act(id=4, screenplay_id=2, position=0)
    created = Scene(id=7, act_id=4, heading="EXT. GARDEN - DAY", position=1)

    async def get_project(_session: _Session, _project_id: int) -> Project:
        """Return the project fixture."""
        return project

    async def get_screenplay(_session: _Session, _screenplay_id: int) -> Screenplay:
        """Return the screenplay fixture."""
        return screenplay

    async def get_act(_session: _Session, _act_id: int) -> Act:
        """Return the act fixture."""
        return act

    async def create_scene(_session: _Session, _data: object) -> Scene:
        """Return the created scene fixture."""
        return created

    monkeypatch.setattr("draftpilot.api.projects.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.projects.screenplays_crud.get", get_screenplay)
    monkeypatch.setattr("draftpilot.api.projects.acts_crud.get", get_act)
    monkeypatch.setattr("draftpilot.api.projects.scenes_crud.create", create_scene)
    response = client.post(
        "/api/v1/projects/9/screenplays/2/scenes",
        json={"act_id": 4, "heading": "EXT. GARDEN - DAY", "position": 1},
    )
    assert response.status_code == 201
    assert response.json()["id"] == 7
    assert response.json()["heading"] == "EXT. GARDEN - DAY"


def test_project_instruction_update_requires_matching_if_match(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Persist project instructions only when the caller holds its current version."""
    project = Project(id=9, title="Story", version=4, project_instruction="Keep it tense.")
    updated = Project(id=9, title="Story", version=5, project_instruction="Keep it intimate.")
    calls: list[object] = []

    async def get_project(_session: _Session, _project_id: int) -> Project:
        """Return the versioned project fixture."""
        return project

    async def update_project(_session: _Session, _project: Project, data: object) -> Project:
        """Capture the instruction update and return the next project version."""
        calls.append(data)
        return updated

    monkeypatch.setattr("draftpilot.api.projects.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.projects.projects_crud.update", update_project)
    response = client.patch(
        "/api/v1/projects/9",
        headers={"If-Match": "4"},
        json={"project_instruction": "Keep it intimate."},
    )
    assert response.status_code == 200
    assert response.json()["project_instruction"] == "Keep it intimate."
    assert response.json()["version"] == 5
    assert len(calls) == 1
    stale = client.patch(
        "/api/v1/projects/9",
        headers={"If-Match": "3"},
        json={"project_instruction": "Overwrite me."},
    )
    assert stale.status_code == 409
    assert len(calls) == 1


def test_project_metadata_update_rejects_primary_translation_overlap(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a metadata edit that makes the primary language a translation target."""
    project = Project(id=9, title="Story", version=4, primary_language="English", languages=["Hindi"])
    calls: list[object] = []

    async def get_project(_session: _Session, _project_id: int) -> Project:
        """Return the current project metadata."""
        return project

    async def update_project(_session: _Session, _project: Project, data: object) -> Project:
        """Capture updates that should not be reached for invalid metadata."""
        calls.append(data)
        return project

    monkeypatch.setattr("draftpilot.api.projects.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.projects.projects_crud.update", update_project)
    response = client.patch(
        "/api/v1/projects/9",
        headers={"If-Match": "4"},
        json={"languages": ["Hindi", "English"]},
    )
    assert response.status_code == 422
    assert calls == []


def test_translation_update_is_scoped_and_preserves_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Save a translation against a dialogue block without replacing source text."""
    scene = Scene(id=7, act_id=4, heading="INT. HOUSE - DAY", version=3)
    act = Act(id=4, screenplay_id=2, position=0)
    screenplay = Screenplay(id=2, project_id=9, title="Story")
    block = Block(id=11, scene_id=7, element_type=BlockType.DIALOGUE, text="We should go.")

    async def get_scene(_session: _Session, _scene_id: int) -> Scene:
        """Return the versioned scene fixture."""
        return scene

    async def get_block(_session: _Session, _block_id: int) -> Block:
        """Return the source dialogue fixture."""
        return block

    async def get_act(_session: _Session, _act_id: int) -> Act:
        """Return the owning act fixture."""
        return act

    async def get_screenplay(_session: _Session, _screenplay_id: int) -> Screenplay:
        """Return the owning screenplay fixture."""
        return screenplay

    async def upsert(_session: _Session, data: object) -> DialogueTranslation:
        """Return a persisted translation fixture."""
        return DialogueTranslation(
            id=21,
            block_id=getattr(data, "block_id"),
            language=getattr(data, "language"),
            text=getattr(data, "text"),
            source_version=getattr(data, "source_version"),
            status=getattr(data, "status"),
        )

    monkeypatch.setattr("draftpilot.api.projects.scenes_crud.get", get_scene)
    monkeypatch.setattr("draftpilot.api.projects.blocks_crud.get", get_block)
    monkeypatch.setattr("draftpilot.api.projects.acts_crud.get", get_act)
    monkeypatch.setattr("draftpilot.api.projects.screenplays_crud.get", get_screenplay)
    monkeypatch.setattr("draftpilot.api.projects.translations_crud.upsert", upsert)
    response = client.put(
        "/api/v1/projects/9/scenes/7/blocks/11/translations/Hindi",
        headers={"If-Match": "3"},
        json={"text": "हमें जाना चाहिए।", "status": "approved"},
    )
    assert response.status_code == 200
    assert response.json()["text"] == "हमें जाना चाहिए।"
    assert response.json()["source_version"] == 3
    assert block.text == "We should go."


def test_start_run_persists_before_enqueue(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Create a durable run and enqueue only its persisted identifier."""
    project = Project(id=9, title="Story")
    run = WorkflowRun(id=31, project_id=9, input={"screenplay_id": 2})
    enqueued: list[tuple[str, int | None]] = []

    async def get_project(_session: _Session, _project_id: int) -> Project:
        """Return the owning project fixture."""
        return project

    async def create_run(_session: _Session, _data: object) -> WorkflowRun:
        """Return the durable run fixture."""
        return run

    async def get_screenplay(_session: _Session, _screenplay_id: int) -> Screenplay:
        """Return a screenplay owned by the project fixture."""
        return Screenplay(id=2, project_id=9, title="Story")

    class Pool:
        """Capture queue submissions without Redis."""

        async def enqueue_job(self, name: str, run_id: int | None) -> None:
            """Record one queued job."""
            enqueued.append((name, run_id))

    async def get_pool() -> Pool:
        """Return the in-memory queue fixture."""
        return Pool()

    monkeypatch.setattr("draftpilot.api.runs.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.runs.screenplays_crud.get", get_screenplay)
    monkeypatch.setattr("draftpilot.api.runs.runs_crud.create", create_run)
    monkeypatch.setattr("draftpilot.api.runs.get_arq_pool", get_pool)
    response = client.post(
        "/api/v1/projects/9/runs", json={"screenplay_id": 2}
    )
    assert response.status_code == 202
    assert response.json()["id"] == 31
    assert enqueued == [("execute_workflow", 31)]


def test_start_run_rejects_screenplay_from_another_project(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prevent a run from crossing project boundaries through its screenplay id."""
    async def get_project(_session: _Session, _project_id: int) -> Project:
        """Return the requested project fixture."""
        return Project(id=9, title="Story")

    async def get_screenplay(_session: _Session, _screenplay_id: int) -> Screenplay:
        """Return a screenplay owned by a different project."""
        return Screenplay(id=2, project_id=10, title="Other story")

    monkeypatch.setattr("draftpilot.api.runs.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.runs.screenplays_crud.get", get_screenplay)
    response = client.post("/api/v1/projects/9/runs", json={"screenplay_id": 2})
    assert response.status_code == 404
    assert response.json()["detail"] == "Screenplay not found"


def test_cancel_run_preserves_durable_history(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transition a queued run to cancelled without deleting its record."""
    run = WorkflowRun(id=31, project_id=9, status="queued")

    async def get_run(_session: _Session, _run_id: int) -> WorkflowRun:
        """Return the queued run fixture."""
        return run

    async def update_status(_session: _Session, value: WorkflowRun, status: str) -> WorkflowRun:
        """Apply the cancellation transition in memory."""
        value.status = status
        return value

    monkeypatch.setattr("draftpilot.api.runs.runs_crud.get", get_run)
    monkeypatch.setattr("draftpilot.api.runs.runs_crud.update_status", update_status)
    response = client.post("/api/v1/projects/9/runs/31/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
