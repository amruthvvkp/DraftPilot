"""Test the provider-backed Copilot response boundary."""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.api.copilot import router
from draftpilot.core.db import async_get_db
from draftpilot.models import CopilotMessage, CopilotMessageCreate, Project, WorkflowRun, WorkflowRunCreate


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

    async def reply(content, page, artifact, selection, role, history, llm_settings=None, retrieved_context=None) -> str:
        """Return a deterministic provider fixture response."""
        assert llm_settings is None
        assert (content, page, artifact, selection, role) == ("Find the causal gap.", "timeline", "outline", "Beat 4", "continuity_supervisor")
        assert history[-1]["content"] == "Find the causal gap."
        assert retrieved_context == []
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


def test_async_copilot_response_enqueues_durable_run(monkeypatch) -> None:
    """Persist a user turn before returning a worker-reconnectable run."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session, None]:
        """Yield an isolated database marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")

    async def get_project(_session: _Session, _project_id: int) -> Project:
        """Return the project fixture."""
        return Project(id=7, title="Durable story")

    async def create_message(_session: _Session, data: CopilotMessageCreate) -> CopilotMessage:
        """Return the persisted user turn fixture."""
        return CopilotMessage(id=8, **data.model_dump())

    async def list_messages(_session: _Session, _project_id: int) -> list[CopilotMessage]:
        """Return no prior turns for the fixture."""
        return []

    async def create_run(_session: _Session, _data: WorkflowRunCreate) -> WorkflowRun:
        """Return a queued durable run fixture."""
        assert _data.input["active_tools"] == ["screenplay.read", "context.read", "revisions.read"]
        return WorkflowRun(id=44, project_id=7, kind="copilot_response")

    class Pool:
        """Capture one queued worker job."""

        async def enqueue_job(self, name: str, run_id: int | None) -> None:
            """Capture the queued worker call."""
            assert (name, run_id) == ("execute_workflow", 44)

    async def get_pool() -> Pool:
        """Return the queue fixture."""
        return Pool()

    monkeypatch.setattr("draftpilot.api.copilot.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.copilot.messages_crud.create", create_message)
    monkeypatch.setattr("draftpilot.api.copilot.messages_crud.list_for_project", list_messages)
    monkeypatch.setattr("draftpilot.api.copilot.runs_crud.create", create_run)
    monkeypatch.setattr("draftpilot.api.copilot.get_arq_pool", get_pool)
    response = TestClient(app).post(
        "/api/v1/projects/7/copilot/messages/respond-async",
        json={"content": "Keep the ending earned.", "page": "workspace"},
    )
    assert response.status_code == 202
    assert response.json()["run"]["kind"] == "copilot_response"
