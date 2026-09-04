"""Test the bounded outbound MCP client boundary."""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from _async import run_async
from draftpilot.core.mcp_client import DraftPilotMCPClient, MCPClientError, _bounded_result, validate_mcp_endpoint


def test_validate_mcp_endpoint_blocks_metadata_and_credentials() -> None:
    """Reject metadata services and URLs containing credentials."""
    with pytest.raises(MCPClientError):
        validate_mcp_endpoint("http://169.254.169.254/mcp")
    with pytest.raises(MCPClientError):
        validate_mcp_endpoint("https://user:secret@example.com/mcp")
    with pytest.raises(MCPClientError):
        validate_mcp_endpoint("http://10.0.0.8:9001/mcp")
    with pytest.raises(MCPClientError):
        validate_mcp_endpoint("http://[fe80::1]:9001/mcp")
    assert validate_mcp_endpoint("http://localhost:9001/mcp") == "http://localhost:9001/mcp"
    assert validate_mcp_endpoint("http://127.0.0.1:9001/mcp") == "http://127.0.0.1:9001/mcp"


def test_bounded_result_rejects_oversized_mcp_payload() -> None:
    """Reject an external response beyond the client output budget."""
    with pytest.raises(MCPClientError):
        _bounded_result("secret-looking payload", 5)


def test_mcp_client_rejects_invalid_prompt_and_resource_inputs() -> None:
    """Bound outbound prompt and resource identifiers before opening a session."""
    client = DraftPilotMCPClient("http://localhost:9001/mcp")
    with pytest.raises(MCPClientError):
        run_async(client.get_prompt(""))
    with pytest.raises(MCPClientError):
        run_async(client.read_resource(""))


def test_mcp_block_proposal_rejects_invalid_semantic_values() -> None:
    """Reject malformed block proposals before opening a database session."""
    from draftpilot.mcp.server import propose_screenplay_change

    with pytest.raises(ValueError, match="block type"):
        run_async(
            propose_screenplay_change(
                9,
                7,
                {"element_type": "not-a-screenplay-element"},
                {},
                object(),
                block_id=11,
            )
        )


def test_mcp_timeline_proposal_persists_with_server_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Persist an external timeline proposal only for the current screenplay order."""
    from draftpilot.mcp import server
    from draftpilot.models import Screenplay, Scene, TimelineProposalRecord

    class SessionScope:
        """Provide a bounded fake database context for the MCP tool."""

        async def __aenter__(self) -> object:
            """Return the isolated session marker."""
            return object()

        async def __aexit__(self, *_args: object) -> None:
            """Close the isolated database context."""

    created = TimelineProposalRecord(
        id=12,
        project_id=9,
        screenplay_id=4,
        original_scene_ids=[7, 8],
        proposed_scene_ids=[8, 7],
        timings=[{"scene_id": 8, "position": 0, "start_seconds": 0, "end_seconds": 45}],
        total_runtime_seconds=75,
    )
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(server, "session_scope", lambda: SessionScope())
    monkeypatch.setattr(server, "authorize_invocation", AsyncMock())
    monkeypatch.setattr(server.screenplays_crud, "get", AsyncMock(return_value=Screenplay(id=4, project_id=9, title="Draft")))
    monkeypatch.setattr(server.scenes_crud, "list_for_screenplay", AsyncMock(return_value=[Scene(id=7, act_id=1, heading="A"), Scene(id=8, act_id=1, heading="B")]))
    monkeypatch.setattr(server.timeline_proposals_crud, "create", create)

    result = run_async(
        server.propose_timeline_reorder(
            9, 4, [7, 8], [8, 7], {7: 30, 8: 45}, SimpleNamespace(client_id="writer")
        )
    )

    assert result["id"] == 12
    assert result["proposed_scene_ids"] == [8, 7]
    record = create.await_args.args[1]
    assert record.original_scene_ids == [7, 8]
    assert record.total_runtime_seconds == 75


def test_mcp_context_workflow_uses_shared_scope_and_queues_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Schedule a typed context workflow through the external MCP boundary."""
    from draftpilot.mcp import server
    from draftpilot.models import Project, StoryArtifact, WorkflowRun

    class SessionScope:
        """Provide a bounded fake database context for context generation."""

        async def __aenter__(self) -> object:
            """Return the isolated session marker."""
            return object()

        async def __aexit__(self, *_args: object) -> None:
            """Close the isolated database context."""

    class Pool:
        """Capture the queued context job."""

        def __init__(self) -> None:
            """Initialize the captured job list."""
            self.jobs: list[tuple[str, int | None]] = []

        async def enqueue_job(self, name: str, run_id: int | None) -> None:
            """Capture a worker job."""
            self.jobs.append((name, run_id))

    pool = Pool()
    run = WorkflowRun(id=44, project_id=9, kind="context_generation")
    monkeypatch.setattr(server, "session_scope", lambda: SessionScope())
    monkeypatch.setattr(server, "authorize_invocation", AsyncMock())
    monkeypatch.setattr(server.projects_crud, "get", AsyncMock(return_value=Project(id=9, title="Draft")))
    monkeypatch.setattr(server.artifacts_crud, "get", AsyncMock(return_value=StoryArtifact(id=3, project_id=9, kind="outline", title="Outline", version=4)))
    monkeypatch.setattr(server.runs_crud, "create", AsyncMock(return_value=run))
    monkeypatch.setattr(server, "get_arq_pool", AsyncMock(return_value=pool))

    result = run_async(server.start_context_workflow(9, "camera", 3, "Plan the reveal.", ctx=SimpleNamespace(client_id="writer")))

    assert result["id"] == 44
    assert pool.jobs == [("execute_workflow", 44)]
