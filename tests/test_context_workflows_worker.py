"""Test provider-backed context workflow execution and review-only results."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from draftpilot.models import StoryArtifact
from _async import run_async


class _Scope:
    """Provide a reusable asynchronous session fixture."""

    def __init__(self, session: object) -> None:
        """Store the isolated session fixture."""
        self.session = session

    async def __aenter__(self) -> object:
        """Return the isolated session."""
        return self.session

    async def __aexit__(self, *args: object) -> None:
        """Close the isolated session fixture."""


def test_context_worker_persists_cited_review_only_result(monkeypatch) -> None:
    """Generate a context suggestion without mutating the source artifact."""
    from draftpilot.worker import functions

    run = SimpleNamespace(
        id=10,
        project_id=7,
        kind="context_generation",
        agent_role="associate_director",
        status="running",
        input={
            "workflow": "camera",
            "instruction": "Plan coverage for the reveal.",
            "artifact_id": 3,
            "source_version": 4,
        },
    )
    session = object()
    source = StoryArtifact(id=3, project_id=7, kind="outline", title="Outline", content="The reveal happens.", version=4)
    monkeypatch.setattr(functions, "session_scope", lambda: _Scope(session))
    monkeypatch.setattr(functions.artifacts_crud, "get", AsyncMock(return_value=source))
    monkeypatch.setattr(functions.workflow_runs_crud, "get", AsyncMock(return_value=run))

    async def update(_session: object, current: object, status: str, result=None, error=None) -> object:
        """Capture the durable workflow transition."""
        current.status = status
        current.result = result
        current.error = error
        return current

    async def context(_project_id: int, _query: str) -> list[dict[str, object]]:
        """Return one citation-bearing retrieval fixture."""
        return [{"citation": {"source_id": "artifact:3", "content_version": 4}}]

    async def reply(*args: object, **kwargs: object) -> str:
        """Return a deterministic provider suggestion fixture."""
        return "Use a slow push into the reveal, then hold on the reaction."

    monkeypatch.setattr(functions.workflow_runs_crud, "update_status", update)
    monkeypatch.setattr(functions, "retrieve_context", context)
    monkeypatch.setattr(functions, "generate_reply", reply)
    result = run_async(functions._execute_context_generation({}, run))

    assert result["workflow"] == "camera"
    assert result["requires_review"] is True
    assert result["citations"] == [{"source_id": "artifact:3", "content_version": 4}]
    assert source.content == "The reveal happens."
    assert run.status == "succeeded"
