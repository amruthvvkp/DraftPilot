"""Test the local stdio MCP server entrypoint."""

import pytest

from draftpilot.mcp import __main__ as mcp_main


def test_stdio_entrypoint_uses_protocol_safe_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start FastMCP with stdio and suppress its human-readable banner."""
    calls: list[dict[str, object]] = []

    def capture(**kwargs: object) -> None:
        """Capture transport options without starting a subprocess."""
        calls.append(kwargs)

    monkeypatch.setattr(mcp_main.mcp, "run", capture)
    mcp_main.main()
    assert calls == [{"transport": "stdio", "show_banner": False}]
