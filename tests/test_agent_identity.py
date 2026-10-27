"""Test the signed internal-agent identity that in-app tool calls carry in their MCP ``_meta``."""

import asyncio
import json

from _async import run_async
from fastmcp import Client, FastMCP

from draftpilot.core.agent_identity import (
    META_KEY,
    InternalAgent,
    acting_as,
    agent_from_meta,
    current_internal_agent,
    identity_meta,
)
from draftpilot.mcp.server import InternalAgentIdentity


def test_a_stamp_round_trips_and_forgeries_do_not() -> None:
    """Only a stamp signed in this process names an agent; edited claims and made-up signatures name nobody."""
    agent = InternalAgent(project_id=3, role="researcher", run_id=9)
    meta = identity_meta(agent)
    assert agent_from_meta(meta) == agent
    stamp = meta[META_KEY]
    other_project = json.dumps({"project_id": 4, "role": "researcher", "run_id": 9}, sort_keys=True)
    assert agent_from_meta({META_KEY: {"claims": other_project, "signature": stamp["signature"]}}) is None
    assert agent_from_meta({META_KEY: {"claims": stamp["claims"], "signature": "0" * 64}}) is None
    assert agent_from_meta({META_KEY: "project 3"}) is None
    assert agent_from_meta(None) is None and agent_from_meta({}) is None


def test_each_call_is_bound_to_its_own_stamp_and_nothing_leaks_from_the_caller() -> None:
    """Concurrent calls on one shared session see their own identity; an unstamped call sees none."""
    server = FastMCP("identity", middleware=[InternalAgentIdentity()])

    @server.tool
    async def whoami() -> str:
        """Report the bound internal agent."""
        await asyncio.sleep(0.01)
        agent = current_internal_agent()
        return f"{agent.project_id}:{agent.role}" if agent else "nobody"

    async def scenario() -> list[str]:
        """Call concurrently with two stamps, then unstamped from inside a caller-side identity."""
        async with Client(server) as client:
            calls = [
                client.call_tool("whoami", {}, meta=identity_meta(InternalAgent(project_id=project, role="room")))
                for project in (1, 2)
            ]
            results = [result.data for result in await asyncio.gather(*calls)]
            with acting_as(InternalAgent(project_id=7, role="leaked")):
                results.append((await client.call_tool("whoami", {})).data)
        return results

    assert run_async(scenario()) == ["1:room", "2:room", "nobody"]
