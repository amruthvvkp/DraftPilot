"""Test the durable, context-bearing Copilot message boundary."""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from draftpilot.api.copilot import router
from draftpilot.core.db import async_get_db
from draftpilot.models import CopilotMessage, CopilotMessageCreate, Project


class _Session:
    """Stand in for an isolated database session."""


def test_copilot_message_persists_full_context_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist page, selection, instructions, citations, and active tools."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session, None]:
        """Yield an isolated database marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    project = Project(id=7, title="Context story")
    captured: list[CopilotMessageCreate] = []
    stored = CopilotMessage(
        id=4,
        project_id=7,
        content="Keep the reveal causal.",
        page="timeline",
        artifact="outline",
        selection="Beat 4",
        instruction_layers={"project": "Stay grounded."},
        citations=[{"source_id": "artifact:3", "content_version": 2}],
        active_tools=["timeline.propose"],
    )

    async def get_project(_session: _Session, _project_id: int) -> Project:
        """Return the project fixture."""
        return project

    async def create(_session: _Session, data: CopilotMessageCreate) -> CopilotMessage:
        """Capture the durable message request."""
        captured.append(data)
        return stored

    monkeypatch.setattr("draftpilot.api.copilot.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.copilot.messages_crud.create", create)
    response = TestClient(app).post(
        "/api/v1/projects/7/copilot/messages",
        json={
            "content": "Keep the reveal causal.",
            "page": "timeline",
            "artifact": "outline",
            "selection": "Beat 4",
            "instruction_layers": {"project": "Stay grounded."},
            "citations": [{"source_id": "artifact:3", "content_version": 2}],
            "active_tools": ["timeline.propose"],
        },
    )
    assert response.status_code == 201
    assert captured[0].page == "timeline"
    assert captured[0].citations[0]["content_version"] == 2
    assert response.json()["active_tools"] == ["timeline.propose"]
