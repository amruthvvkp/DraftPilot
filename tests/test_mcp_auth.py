"""Test constant-time MCP token validation."""

from pydantic import SecretStr

from draftpilot.core.mcp_auth import client_id_for_token, valid_static_token


def test_static_token_requires_exact_non_empty_match() -> None:
    """Accept only the configured non-empty token."""
    assert valid_static_token("secret", "secret")
    assert not valid_static_token("wrong", "secret")
    assert not valid_static_token("", "secret")
    assert not valid_static_token("secret", "")


def test_client_token_resolves_distinct_registered_identity() -> None:
    """Resolve per-client tokens without sharing the default MCP identity."""
    tokens = {"claude": SecretStr("claude-secret")}
    assert client_id_for_token("claude-secret", "default", tokens) == "claude"
    assert client_id_for_token("default", "default", tokens) == "mcp-client"
    assert client_id_for_token("unknown", "default", tokens) is None
