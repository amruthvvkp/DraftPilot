"""Develop a short screenplay end to end over MCP against a running stack, the way an external agent would.

    uv run python scripts/mcp_journey.py                     # against http://localhost:9001/mcp and :9000
    DRAFTPILOT_MCP_ENDPOINT=... DRAFTPILOT_API=... uv run python scripts/mcp_journey.py

It creates a project, develops the storyline, cast (with a timeline and a relationship), acts and
beats, writes two scenes from Fountain, snapshots and diffs a revision, reviews the outline and
exports Fountain. Writes that need the writer's approval are approved through the studio's REST
API, as the writer would in the studio. Needs an installation-wide grant for the MCP client:
``uv run draftpilot-mcp trust mcp-client`` (the client the default ``MCP__AUTH_TOKEN`` maps to).
"""

import asyncio
import os
import re
import sys
from typing import Any

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

MCP = os.environ.get("DRAFTPILOT_MCP_ENDPOINT", "http://localhost:9001/mcp")
TOKEN = os.environ.get("DRAFTPILOT_MCP_TOKEN", "draftpilot-local-token")
API = os.environ.get("DRAFTPILOT_API", "http://localhost:9000/api/v1")
API_TOKEN = os.environ.get("API__TOKEN", "")
PENDING = re.compile(r"approval request (\d+) is pending")


class Journey:
    """Call tools as an external agent, approving gated writes as the writer."""

    def __init__(self, client: Client, api: httpx.AsyncClient) -> None:
        """Wrap the MCP client and the writer's REST session."""
        self.client, self.api = client, api
        self.approvals = 0

    async def call(self, tool: str, **arguments: Any) -> Any:
        """Call one tool; approve it as the writer and retry when it needs approval."""
        try:
            result = await self.client.call_tool(tool, arguments)
        except ToolError as exc:
            match = PENDING.search(str(exc))
            if match is None:
                raise
            approval_id = int(match.group(1))
            response = await self.api.post(f"/projects/{arguments['project_id']}/mcp-approvals/{approval_id}/approve")
            response.raise_for_status()
            self.approvals += 1
            result = await self.client.call_tool(tool, {**arguments, "approval_id": approval_id})
        data = result.structured_content
        return data["result"] if isinstance(data, dict) and set(data) == {"result"} else data


async def journey() -> None:
    """Run the journey and print what it built."""
    headers = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}
    transport = StreamableHttpTransport(MCP, headers={"Authorization": f"Bearer {TOKEN}"})
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30) as api, Client(transport) as client:
        dp = Journey(client, api)
        project = await dp.call("create_project", title="MCP journey: The Lighthouse", logline="A keeper's daughter must let the light go dark to save a ship.")
        pid = project["id"]
        print(f"project {pid}")
        project = await dp.call(
            "update_project",
            project_id=pid,
            fields={"premise": "Can you keep a promise by breaking it?", "theme": "Duty against love", "tone": "Windswept, quiet, hopeful"},
            expected_version=project["version"],
        )
        mara = await dp.call("create_story_entity", project_id=pid, kind="character", fields={"name": "Mara", "role": "protagonist", "want": "Keep the light burning", "need": "Choose her own life", "objective": "Bring the ship in"})
        tom = await dp.call("create_story_entity", project_id=pid, kind="character", fields={"name": "Tom", "role": "supporting", "want": "His daughter safe"})
        await dp.call("create_story_entity", project_id=pid, kind="relationship", fields={"source_character_id": tom["id"], "target_character_id": mara["id"], "relation": "father of"})
        await dp.call("create_story_entity", project_id=pid, kind="timeline_event", fields={"character_id": mara["id"], "title": "Promises to tend the light", "story_time": "Night 1"})
        outline = await dp.call("read_outline", project_id=pid)
        act_one = outline["acts"][0]["id"]
        act_two = (await dp.call("create_act", project_id=pid, title="Act Two"))["id"]
        storm = await dp.call("create_story_entity", project_id=pid, kind="beat", fields={"title": "The storm", "act_id": act_one})
        await dp.call("create_story_entity", project_id=pid, kind="beat", fields={"title": "The ship", "act_id": act_two})
        scene = await dp.call(
            "create_scene",
            project_id=pid,
            heading="INT. LIGHTHOUSE - NIGHT",
            act_id=act_one,
            fountain="Rain hammers the glass. MARA, 17, winds the clockwork.\n\nTOM (O.S.)\nKeep it turning.\n\nMARA\nI always do.",
        )
        await dp.call("update_story_entity", project_id=pid, kind="beat", entity_id=storm["id"], fields={"scene_ids": [scene["id"]], "status": "drafted"}, expected_version=storm["version"])
        first = await dp.call("snapshot_scene", project_id=pid, scene_id=scene["id"], message="first pass")
        written = await dp.call(
            "write_scene", project_id=pid, scene_id=scene["id"], expected_version=scene["version"],
            fountain="INT. LIGHTHOUSE - NIGHT\n\nRain. MARA, 17, winds the clockwork, hands raw.\n\nMARA\nI always do.",
        )
        second = await dp.call("snapshot_scene", project_id=pid, scene_id=scene["id"], message="tighter")
        diff = await dp.call("diff_scene_revisions", project_id=pid, scene_id=scene["id"], revision_id=first["id"], other_revision_id=second["id"])
        assert "hands raw" in diff["diff"], diff
        await dp.call("create_scene", project_id=pid, heading="EXT. ROCKS - NIGHT", act_id=act_two, fountain="A ship's bell, close. Too close.")
        context = await dp.call("read_story_context", project_id=pid)
        assert "Mara" in context["story"] and "Duty against love" in context["story"], context
        overview = await dp.call("read_project_overview", project_id=pid)
        draft = overview["drafts"][0]
        assert draft["scene_count"] == 2 and written["heading"] == "INT. LIGHTHOUSE - NIGHT", overview
        export = await dp.call("render_screenplay_export", project_id=pid, screenplay_id=draft["screenplay_id"], file_format="fountain")
        text = str(export["content"])
        assert "INT. LIGHTHOUSE - NIGHT" in text and "MARA" in text, text[:500]
        print(f"ok: {dp.approvals} writer approvals; scenes, cast, outline and export verified for project {pid}")


if __name__ == "__main__":
    try:
        asyncio.run(journey())
    except (ToolError, AssertionError, httpx.HTTPError) as exc:
        print(f"journey failed: {exc}", file=sys.stderr)
        sys.exit(1)
