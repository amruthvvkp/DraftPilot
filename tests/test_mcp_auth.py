"""Test constant-time MCP token validation."""

from draftpilot.core.mcp_auth import valid_static_token


def test_static_token_requires_exact_non_empty_match() -> None:
    """Accept only the configured non-empty token."""
    assert valid_static_token("secret", "secret")
    assert not valid_static_token("wrong", "secret")
    assert not valid_static_token("", "secret")
    assert not valid_static_token("secret", "")
