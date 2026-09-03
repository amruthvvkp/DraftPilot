"""Bounded outbound MCP client transports for DraftPilot agents."""

import ipaddress
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from pydantic import AnyUrl


class MCPClientError(ValueError):
    """Describe an invalid or oversized outbound MCP response."""


def validate_mcp_endpoint(endpoint: str) -> str:
    """Validate an MCP HTTP endpoint while blocking cloud metadata targets."""
    parsed = urlsplit(endpoint)
    blocked_hosts = {
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.google.com",
    }
    hostname = parsed.hostname
    unsafe_literal = False
    if hostname:
        try:
            address = ipaddress.ip_address(hostname)
            unsafe_literal = (
                address.is_private
                or address.is_link_local
                or address.is_reserved
                or address.is_multicast
            ) and not address.is_loopback
        except ValueError:
            pass
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username
        or parsed.password
        or hostname.casefold() in blocked_hosts
        or unsafe_literal
    ):
        raise MCPClientError("MCP endpoint must be an HTTP(S) URL without embedded credentials")
    return endpoint.rstrip("/")


def _bounded_result(value: object, max_output_chars: int) -> dict[str, object] | list[object] | str:
    """Serialize one MCP result and reject output beyond the configured bound."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")  # type: ignore[union-attr]
    if isinstance(value, (dict, list, str)):
        result: dict[str, object] | list[object] | str = value
    else:
        result = str(value)
    if len(json.dumps(result, ensure_ascii=False, default=str)) > max_output_chars:
        raise MCPClientError("MCP response exceeds the configured output limit")
    return result


class DraftPilotMCPClient:
    """Call external MCP servers through authenticated, bounded transports."""

    def __init__(
        self,
        endpoint: str,
        token: str = "",
        timeout_seconds: float = 10.0,
        max_output_chars: int = 100_000,
    ) -> None:
        """Configure an authenticated Streamable HTTP MCP client."""
        if timeout_seconds <= 0 or max_output_chars <= 0:
            raise MCPClientError("MCP timeout and output limit must be positive")
        self.endpoint = validate_mcp_endpoint(endpoint)
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    @asynccontextmanager
    async def _http_session(self) -> AsyncIterator[ClientSession]:
        """Open and initialize one authenticated Streamable HTTP session."""
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        async with streamablehttp_client(
            self.endpoint,
            headers=headers,
            timeout=self.timeout_seconds,
            sse_read_timeout=self.timeout_seconds,
        ) as (read_stream, write_stream, _session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    @asynccontextmanager
    async def _stdio_session(
        self, command: str, args: list[str]
    ) -> AsyncIterator[ClientSession]:
        """Open and initialize one explicitly selected local stdio session."""
        if not command or any("\x00" in value for value in [command, *args]):
            raise MCPClientError("Invalid stdio MCP command")
        parameters = StdioServerParameters(command=command, args=args)
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    async def list_tools(self) -> dict[str, object] | list[object] | str:
        """Discover external MCP tools through Streamable HTTP."""
        async with self._http_session() as session:
            return _bounded_result(await session.list_tools(), self.max_output_chars)

    async def list_prompts(self) -> dict[str, object] | list[object] | str:
        """Discover external MCP prompts through Streamable HTTP."""
        async with self._http_session() as session:
            return _bounded_result(await session.list_prompts(), self.max_output_chars)

    async def list_resources(self) -> dict[str, object] | list[object] | str:
        """Discover external MCP resources through Streamable HTTP."""
        async with self._http_session() as session:
            return _bounded_result(await session.list_resources(), self.max_output_chars)

    async def read_resource(self, uri: str) -> dict[str, object] | list[object] | str:
        """Read one bounded external MCP resource by URI."""
        if not uri or len(uri) > 2_000:
            raise MCPClientError("MCP resource URI is invalid")
        async with self._http_session() as session:
            try:
                resource_uri = AnyUrl(uri)
            except ValueError as exc:
                raise MCPClientError("MCP resource URI is invalid") from exc
            return _bounded_result(
                await session.read_resource(resource_uri), self.max_output_chars
            )

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None = None
    ) -> dict[str, object] | list[object] | str:
        """Render one external MCP prompt with bounded string arguments."""
        if not name or len(name) > 200:
            raise MCPClientError("MCP prompt name is invalid")
        if arguments and any(len(key) > 200 or len(value) > 10_000 for key, value in arguments.items()):
            raise MCPClientError("MCP prompt arguments are invalid")
        async with self._http_session() as session:
            return _bounded_result(
                await session.get_prompt(name, arguments or {}), self.max_output_chars
            )

    async def call_tool(
        self, name: str, arguments: dict[str, object] | None = None
    ) -> dict[str, object] | list[object] | str:
        """Call one external MCP tool with a bounded typed argument map."""
        if not name or len(name) > 200:
            raise MCPClientError("MCP tool name is invalid")
        async with self._http_session() as session:
            return _bounded_result(
                await session.call_tool(name, arguments or {}), self.max_output_chars
            )

    async def call_stdio_tool(
        self,
        command: str,
        args: list[str],
        name: str,
        arguments: dict[str, object] | None = None,
    ) -> dict[str, object] | list[object] | str:
        """Call one explicitly configured local stdio MCP tool."""
        if not name or len(name) > 200:
            raise MCPClientError("MCP tool name is invalid")
        async with self._stdio_session(command, args) as session:
            return _bounded_result(
                await session.call_tool(name, arguments or {}), self.max_output_chars
            )
