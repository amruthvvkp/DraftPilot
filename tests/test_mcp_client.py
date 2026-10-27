"""Test the bounded outbound MCP client boundary."""

import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from _async import run_async

from draftpilot.core.mcp_client import (
    DraftPilotMCPClient,
    MCPClientError,
    _bounded_result,
    validate_mcp_endpoint,
)


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


def test_validate_mcp_endpoint_blocks_private_dns_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject a hostname that resolves to a private non-loopback address."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 9001))],
    )
    with pytest.raises(MCPClientError):
        validate_mcp_endpoint("https://mcp.example.test/mcp")


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
    from draftpilot.models import Scene, Screenplay, TimelineProposalRecord

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

        async def start_workflow(self, name: str, *, args: list[object], **_options: object) -> None:
            """Capture a worker job."""
            self.jobs.append((name, args[0]))

    pool = Pool()
    run = WorkflowRun(id=44, project_id=9, kind="context_generation")
    monkeypatch.setattr(server, "session_scope", lambda: SessionScope())
    monkeypatch.setattr(server, "authorize_invocation", AsyncMock())
    monkeypatch.setattr(server.projects_crud, "get", AsyncMock(return_value=Project(id=9, title="Draft")))
    monkeypatch.setattr(server.artifacts_crud, "get", AsyncMock(return_value=StoryArtifact(id=3, project_id=9, kind="outline", title="Outline", version=4)))
    monkeypatch.setattr(server.runs_crud, "create", AsyncMock(return_value=run))
    monkeypatch.setattr("draftpilot.core.temporal.get_client", AsyncMock(return_value=pool))

    result = run_async(server.start_context_workflow(9, "camera", 3, "Plan the reveal.", ctx=SimpleNamespace(client_id="writer")))

    assert result["id"] == 44
    assert pool.jobs == [("execute_workflow", 44)]


def test_mcp_context_apply_requires_approval_and_refreshes_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Require writer approval before applying a context suggestion externally."""
    from draftpilot.mcp import server
    from draftpilot.models import KnowledgeNode, WorkflowRun

    class SessionScope:
        """Provide a bounded fake database context for context application."""

        async def __aenter__(self) -> object:
            """Return the isolated session marker."""
            return object()

        async def __aexit__(self, *_args: object) -> None:
            """Close the isolated database context."""

    class Pool:
        """Capture the canonical graph refresh job."""

        def __init__(self) -> None:
            """Initialize the captured job list."""
            self.jobs: list[tuple[str, object]] = []

        async def start_workflow(self, name: str, *, args: list[object], **_options: object) -> None:
            """Capture one RAG refresh job."""
            self.jobs.append((name, args[0]))

    run = WorkflowRun(id=44, project_id=9, kind="context_generation", status="succeeded", input={"artifact_id": 3}, result={"suggestion": "Use a long lens.", "output_kind": "camera", "source_version": 4, "citations": []})
    node = KnowledgeNode(id=51, project_id=9, kind="camera", label="Camera from run 44", description="Use a long lens.")
    pool = Pool()
    update = AsyncMock()
    monkeypatch.setattr(server, "session_scope", lambda: SessionScope())
    from draftpilot.core.authorization import ApprovalRequiredError

    authorize = AsyncMock(side_effect=[ApprovalRequiredError(7), None])
    monkeypatch.setattr(server, "authorize_invocation", authorize)
    monkeypatch.setattr(server.runs_crud, "get", AsyncMock(return_value=run))
    monkeypatch.setattr(server.artifacts_crud, "get", AsyncMock(return_value=SimpleNamespace(id=3, project_id=9, version=4)))
    monkeypatch.setattr(server.graph_crud, "create_node", AsyncMock(return_value=node))
    monkeypatch.setattr(server.runs_crud, "update_status", update)
    monkeypatch.setattr("draftpilot.core.temporal.get_client", AsyncMock(return_value=pool))

    with pytest.raises(ValueError, match="approval_id=7"):
        run_async(server.apply_context_workflow(9, 44, 4, ctx=SimpleNamespace(client_id="writer")))
    result = run_async(server.apply_context_workflow(9, 44, 4, approval_id=7, ctx=SimpleNamespace(client_id="writer")))

    assert authorize.await_args.kwargs["approval_id"] == 7
    assert authorize.await_args.kwargs["arguments"] == {"run_id": 44, "expected_source_version": 4}
    assert result["node"]["id"] == 51
    assert pool.jobs[0][0] == "index_rag_document"
    assert update.await_args.args[2] == "applied"


def test_mcp_server_resolves_client_id_from_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve authorization scope when FastMCP request metadata is absent."""
    from fastmcp.server.auth import AccessToken

    from draftpilot.mcp import server

    monkeypatch.setattr(
        server,
        "get_access_token",
        lambda: AccessToken(token="redacted", client_id="external-writer", scopes=[]),
    )
    assert server._client_id(SimpleNamespace(client_id=None)) == "external-writer"


def test_mcp_server_uses_configured_stdio_client_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve local stdio calls to the explicitly configured grant identity."""
    from draftpilot.mcp import server

    monkeypatch.setattr(server.settings.mcp, "stdio_client_id", "local-writer")
    monkeypatch.setattr(server, "get_access_token", lambda: None)
    assert server._client_id(SimpleNamespace(client_id=None)) == "local-writer"


def test_mcp_client_methods_with_mocked_http_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise list_tools, list_prompts, list_resources, read_resource, get_prompt, and call_tool."""
    from contextlib import asynccontextmanager

    mock_session = AsyncMock()
    mock_session.list_tools.return_value = {"tools": [{"name": "read_project_artifacts"}]}
    mock_session.list_prompts.return_value = {"prompts": [{"name": "workflow_turn"}]}
    mock_session.list_resources.return_value = {"resources": [{"uri": "draftpilot://context-workflows"}]}
    mock_session.read_resource.return_value = {"contents": [{"text": "artifact-content"}]}
    mock_session.get_prompt.return_value = {"messages": [{"role": "user", "content": "turn"}]}
    mock_session.call_tool.return_value = {"content": [{"type": "text", "text": "result"}]}

    @asynccontextmanager
    async def fake_http_session() -> AsyncMock:
        """Yield the mock session."""
        yield mock_session

    client = DraftPilotMCPClient("http://localhost:9001/mcp", token="secret-token")
    monkeypatch.setattr(client, "_http_session", fake_http_session)

    tools = run_async(client.list_tools())
    assert tools == {"tools": [{"name": "read_project_artifacts"}]}

    prompts = run_async(client.list_prompts())
    assert prompts == {"prompts": [{"name": "workflow_turn"}]}

    resources = run_async(client.list_resources())
    assert resources == {"resources": [{"uri": "draftpilot://context-workflows"}]}

    res_content = run_async(client.read_resource("draftpilot://projects/1/artifacts"))
    assert res_content == {"contents": [{"text": "artifact-content"}]}

    prompt_content = run_async(client.get_prompt("workflow_turn", {"scope": "scene"}))
    assert prompt_content == {"messages": [{"role": "user", "content": "turn"}]}

    tool_call = run_async(client.call_tool("read_project_artifacts", {"project_id": 1}))
    assert tool_call == {"content": [{"type": "text", "text": "result"}]}


def test_mcp_client_call_stdio_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise call_stdio_tool with mocked stdio session."""
    from contextlib import asynccontextmanager

    mock_session = AsyncMock()
    mock_session.call_tool.return_value = {"content": [{"type": "text", "text": "stdio-result"}]}

    @asynccontextmanager
    async def fake_stdio_session(command: str, args: list[str]) -> AsyncMock:
        """Yield the mock session."""
        yield mock_session

    client = DraftPilotMCPClient("http://localhost:9001/mcp")
    monkeypatch.setattr(client, "_stdio_session", fake_stdio_session)

    result = run_async(
        client.call_stdio_tool("python", ["-m", "draftpilot.mcp"], "read_project_artifacts", {"project_id": 1})
    )
    assert result == {"content": [{"type": "text", "text": "stdio-result"}]}


def test_mcp_client_validates_constructor_and_stdio_parameters() -> None:
    """Reject invalid timeout, character bounds, and stdio commands with NUL bytes."""
    with pytest.raises(MCPClientError, match="positive"):
        DraftPilotMCPClient("http://localhost:9001/mcp", timeout_seconds=0)

    with pytest.raises(MCPClientError, match="positive"):
        DraftPilotMCPClient("http://localhost:9001/mcp", max_output_chars=-1)

    client = DraftPilotMCPClient("http://localhost:9001/mcp")
    with pytest.raises(MCPClientError, match="stdio MCP command"):
        async def call_empty() -> None:
            async with client._stdio_session("", []):
                pass
        run_async(call_empty())

    with pytest.raises(MCPClientError, match="stdio MCP command"):
        async def call_nul() -> None:
            async with client._stdio_session("cmd\x00", []):
                pass
        run_async(call_nul())
