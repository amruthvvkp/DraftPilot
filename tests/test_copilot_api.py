"""Test the durable, context-bearing Copilot message boundary."""

from collections.abc import AsyncGenerator
from typing import Self

import pytest
from _async import run_async
from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.copilot import router
from draftpilot.core.copilot import retrieve_context
from draftpilot.core.db import async_get_db
from draftpilot.models import CopilotMessage, CopilotMessageCreate, Project


class _Session:
    """Stand in for an isolated database session."""


def test_retrieve_context_returns_bounded_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Translate the RAG response into project-scoped provider context."""
    class Response:
        """Return a deterministic RAG payload."""

        content = b"{}"

        def raise_for_status(self) -> None:
            """Accept the fixture response."""

        def json(self) -> dict[str, object]:
            """Return one citation-bearing result."""
            return {"results": [{"text": "The reveal is seeded.", "citation": {"source_id": "artifact:3"}}]}

    class Client:
        """Capture one isolated RAG request."""

        def __init__(self, **kwargs: object) -> None:
            """Accept the bounded client configuration."""
            assert kwargs["timeout"] == 3.0

        async def __aenter__(self) -> Self:
            """Enter the HTTP fixture context."""
            return self

        async def __aexit__(self, _type: object, _value: object, _traceback: object) -> None:
            """Leave the HTTP fixture context."""

        async def post(self, url: str, **kwargs: object) -> Response:
            """Return the fixture payload for the expected project query."""
            assert url.endswith("/projects/7/search")
            assert kwargs["json"] == {"query": "Find the reveal", "limit": 8}
            return Response()

    monkeypatch.setattr("draftpilot.core.rag_client.httpx.AsyncClient", Client)
    assert run_async(retrieve_context(7, "Find the reveal"))[0]["citation"] == {"source_id": "artifact:3"}


def test_copilot_message_persists_full_context_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist page, selection, instructions, citations, and active tools."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session]:
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
    async def retrieve(_project_id: int, _query: str) -> list[dict[str, object]]:
        """Return one bounded retrieval fixture."""
        return [{"text": "The reveal is seeded.", "citation": {"source_id": "artifact:3"}}]

    monkeypatch.setattr("draftpilot.api.copilot.retrieve_context", retrieve)
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
