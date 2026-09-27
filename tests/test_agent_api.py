"""Test typed agent screenplay proposal endpoints."""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.agent import router
from draftpilot.core.db import async_get_db
from draftpilot.models import AgentProposal, BlockType, WorkflowRun


class _Session:
    """Stand in for the isolated proposal session."""

    def add(self, _value: object) -> None:
        """Accept a pending model mutation."""

    async def commit(self) -> None:
        """Commit the isolated model mutation."""

    async def refresh(self, _value: object) -> None:
        """Refresh the isolated model mutation."""


def _client() -> TestClient:
    """Build a proposal API client with an isolated database dependency."""
    app = FastAPI()

    async def dependency() -> AsyncGenerator[_Session]:
        """Yield an isolated session marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_block_proposal_captures_scene_version_and_before_snapshot(monkeypatch) -> None:
    """Create a semantic block proposal without applying its operation."""
    scene = SimpleNamespace(id=7, version=3)
    block = SimpleNamespace(id=11, scene_id=7, element_type=BlockType.ACTION, text="A door opens.")
    proposal = AgentProposal(
        id=20,
        project_id=9,
        target_kind="block",
        target_id=11,
        operation={"element_type": "dialogue"},
        diff={"from": "action", "to": "dialogue"},
        before={"scene_id": 7, "element_type": "action"},
        base_version=3,
    )

    monkeypatch.setattr("draftpilot.api.agent._block_target", AsyncMock(return_value=(scene, block)))

    async def create(_session: object, created: AgentProposal) -> AgentProposal:
        """Return the captured proposal fixture."""
        assert created.target_kind == "block"
        assert created.base_version == 3
        assert created.before == {"scene_id": 7, "element_type": "action"}
        return proposal

    monkeypatch.setattr("draftpilot.api.agent.proposals_crud.create", create)
    response = _client().post(
        "/api/v1/projects/9/agent-proposals",
        json={
            "target_kind": "block",
            "target_id": 11,
            "scene_id": 7,
            "operation": {"element_type": "dialogue"},
            "diff": {"from": "action", "to": "dialogue"},
            "base_version": 3,
        },
    )
    assert response.status_code == 201
    assert response.json()["target_kind"] == "block"


def test_block_approval_and_rollback_refresh_the_canonical_scene(monkeypatch) -> None:
    """Refresh RAG after applying and reversing a semantic block proposal."""
    scene = SimpleNamespace(id=7, version=3, heading="INT. ROOM - DAY", body="")
    block = SimpleNamespace(
        id=11,
        scene_id=7,
        element_type=BlockType.ACTION,
        text="A door opens.",
    )
    proposal = AgentProposal(
        id=20,
        project_id=9,
        target_kind="block",
        target_id=11,
        operation={"element_type": "dialogue", "text": "HELLO"},
        diff={},
        before={"scene_id": 7, "element_type": "action", "text": "A door opens."},
        base_version=3,
    )
    monkeypatch.setattr("draftpilot.api.agent._block_target", AsyncMock(return_value=(scene, block)))
    enqueue = AsyncMock()
    monkeypatch.setattr("draftpilot.api.agent._enqueue_rag_index", enqueue)
    monkeypatch.setattr("draftpilot.api.agent.proposals_crud.get", AsyncMock(return_value=proposal))

    client = _client()
    approved = client.post("/api/v1/projects/9/agent-proposals/20/approve")

    assert approved.status_code == 200
    assert proposal.status == "approved"
    assert scene.version == 4
    assert block.element_type == BlockType.DIALOGUE
    assert block.text == "HELLO"
    enqueue.assert_awaited_once_with(9, "scene:7", "scene", "INT. ROOM - DAY\nHELLO", 4)

    rolled_back = client.post("/api/v1/projects/9/agent-proposals/20/rollback")

    assert rolled_back.status_code == 200
    assert proposal.status == "rolled_back"
    assert scene.version == 5
    assert block.element_type == BlockType.ACTION
    assert block.text == "A door opens."
    assert enqueue.await_count == 2
    assert enqueue.await_args_list[1].args == (9, "scene:7", "scene", "INT. ROOM - DAY\nA door opens.", 5)


def test_chat_only_run_cannot_create_agent_proposal(monkeypatch) -> None:
    """Enforce the originating run permission before persisting a proposal."""
    monkeypatch.setattr(
        "draftpilot.api.agent.runs_crud.get",
        AsyncMock(return_value=WorkflowRun(id=31, project_id=9, permission_mode="chat_only")),
    )
    response = _client().post(
        "/api/v1/projects/9/agent-proposals",
        json={
            "target_kind": "block",
            "target_id": 11,
            "scene_id": 7,
            "operation": {"text": "No mutation"},
            "base_version": 1,
            "run_id": 31,
        },
    )
    assert response.status_code == 403


def test_suggest_run_can_create_reviewable_agent_proposal(monkeypatch) -> None:
    """Allow a suggest-mode run to create a proposal for writer review."""
    monkeypatch.setattr(
        "draftpilot.api.agent.runs_crud.get",
        AsyncMock(return_value=WorkflowRun(id=31, project_id=9, permission_mode="suggest")),
    )
    scene = SimpleNamespace(id=7, version=1)
    block = SimpleNamespace(id=11, scene_id=7, element_type=BlockType.ACTION, text="A door opens.")
    monkeypatch.setattr("draftpilot.api.agent._block_target", AsyncMock(return_value=(scene, block)))
    proposal = AgentProposal(
        id=32,
        project_id=9,
        run_id=31,
        target_kind="block",
        target_id=11,
        operation={"text": "A door closes."},
        before={"scene_id": 7, "text": "A door opens."},
        base_version=1,
    )
    monkeypatch.setattr("draftpilot.api.agent.proposals_crud.create", AsyncMock(return_value=proposal))
    response = _client().post(
        "/api/v1/projects/9/agent-proposals",
        json={
            "target_kind": "block",
            "target_id": 11,
            "scene_id": 7,
            "operation": {"text": "A door closes."},
            "base_version": 1,
            "run_id": 31,
        },
    )
    assert response.status_code == 201
    assert response.json()["run_id"] == 31


def test_scoped_edit_run_cannot_target_another_block(monkeypatch) -> None:
    """Reject a proposal whose target is outside the persisted run scope."""
    monkeypatch.setattr(
        "draftpilot.api.agent.runs_crud.get",
        AsyncMock(
            return_value=WorkflowRun(
                id=31,
                project_id=9,
                permission_mode="scoped_edit",
                input={"scope": {"target_kind": "block", "target_id": 12, "scene_id": 7}},
            )
        ),
    )
    response = _client().post(
        "/api/v1/projects/9/agent-proposals",
        json={
            "target_kind": "block",
            "target_id": 11,
            "scene_id": 7,
            "operation": {"text": "Outside scope"},
            "base_version": 1,
            "run_id": 31,
        },
    )
    assert response.status_code == 403


def test_rejecting_a_pending_proposal_leaves_its_target_untouched(monkeypatch) -> None:
    """Reject a pending proposal once; a decided proposal cannot be rejected again."""
    proposal = AgentProposal(
        id=21,
        project_id=9,
        target_kind="block",
        target_id=11,
        operation={"text": "HELLO"},
        diff={},
        before={"scene_id": 7, "text": "A door opens."},
        base_version=3,
    )
    target = AsyncMock()
    monkeypatch.setattr("draftpilot.api.agent._block_target", target)
    monkeypatch.setattr("draftpilot.api.agent.proposals_crud.get", AsyncMock(return_value=proposal))

    client = _client()
    rejected = client.post("/api/v1/projects/9/agent-proposals/21/reject")

    assert rejected.status_code == 200
    assert proposal.status == "rejected"
    target.assert_not_awaited()
    assert client.post("/api/v1/projects/9/agent-proposals/21/reject").status_code == 409
    assert client.post("/api/v1/projects/9/agent-proposals/21/approve").status_code == 409
