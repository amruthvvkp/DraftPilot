"""Test the provider-backed Copilot response boundary."""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.api.copilot import router
from draftpilot.core.db import async_get_db
from draftpilot.models import CopilotMessage, CopilotMessageCreate, Project


class _Session:
    """Stand in for an isolated database session."""


def test_copilot_response_persists_user_and_assistant_turns(monkeypatch) -> None:
    """Generate an assistant reply with the current page and selected role context."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session, None]:
        """Yield an isolated database marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    captured: list[CopilotMessageCreate] = []

    async def get_project(_session: _Session, _project_id: int) -> Project:
        """Return the project fixture."""
        return Project(id=7, title="Reply story")

    async def create(_session: AsyncSession, data: CopilotMessageCreate) -> CopilotMessage:
        """Capture and return each durable turn."""
        captured.append(data)
        return CopilotMessage(id=len(captured), **data.model_dump())

    async def list_messages(_session: _Session, _project_id: int) -> list[CopilotMessage]:
        """Return the captured conversation history."""
        return [
            CopilotMessage(id=1, project_id=7, content="Earlier decision."),
            *[CopilotMessage(id=index + 2, **message.model_dump()) for index, message in enumerate(captured)],
        ]

    async def reply(content, page, artifact, selection, role, history) -> str:
        """Return a deterministic provider fixture response."""
        assert (content, page, artifact, selection, role) == ("Find the causal gap.", "timeline", "outline", "Beat 4", "continuity_supervisor")
        assert history[-1]["content"] == "Find the causal gap."
        return "The reveal needs a stronger setup."

    monkeypatch.setattr("draftpilot.api.copilot.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.copilot.messages_crud.create", create)
    monkeypatch.setattr("draftpilot.api.copilot.messages_crud.list_for_project", list_messages)
    monkeypatch.setattr("draftpilot.api.copilot.generate_reply", reply)
    response = TestClient(app).post(
        "/api/v1/projects/7/copilot/messages/respond",
        json={
            "content": "Find the causal gap.",
            "page": "timeline",
            "artifact": "outline",
            "selection": "Beat 4",
            "instruction_layers": {"agent_role": "continuity_supervisor"},
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "assistant"
    assert len(captured) == 2
