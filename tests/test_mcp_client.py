"""Test the bounded outbound MCP client boundary."""

import pytest

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
