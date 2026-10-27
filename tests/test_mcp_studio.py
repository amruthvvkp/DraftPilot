"""Test the full MCP studio surface: REST parity, an end-to-end screenplay journey, and access boundaries."""

import re
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from _async import run_async
from _db import memory_session
from fastmcp import Client
from fastmcp.exceptions import ToolError
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.api.app import create_app
from draftpilot.core.agent_identity import InternalAgent, identity_meta
from draftpilot.crud.mcp_access import decide_approval
from draftpilot.mcp import server, studio_tools
from draftpilot.models import MCPClient, MCPGrant

# Every REST operation, mapped to the MCP tool that covers it, or to why it is not an MCP tool.
EXEMPT = "exempt"
PARITY: dict[str, str] = {
    "GET /agents/roles": "list_room_workflows",
    "POST /auth/session": EXEMPT + ": browser login",
    "DELETE /auth/session": EXEMPT + ": browser logout",
    "GET /auth/status": EXEMPT + ": browser login",
    "GET /capabilities": EXEMPT + ": published as the draftpilot://capabilities resource",
    "POST /mcp/clients": EXEMPT + ": MCP administration needs the admin token, never a client",
    "GET /mcp/grants": EXEMPT + ": MCP administration",
    "POST /mcp/grants": EXEMPT + ": MCP administration",
    "DELETE /mcp/grants/{grant_id}": EXEMPT + ": MCP administration",
    "GET /mcp/projects/{project_id}/grants": EXEMPT + ": MCP administration",
    "POST /mcp/projects/{project_id}/grants": EXEMPT + ": MCP administration",
    "DELETE /mcp/projects/{project_id}/grants/{grant_id}": EXEMPT + ": MCP administration",
    "GET /projects": "list_projects",
    "POST /projects": "create_project",
    "GET /projects/deleted": EXEMPT + ": recovering deleted projects is the writer's call",
    "POST /projects/deleted/{project_id}/dismiss": EXEMPT + ": writer UI housekeeping",
    "POST /projects/wizard/assist": EXEMPT + ": an LLM helper for the human wizard; MCP clients are the LLM",
    "DELETE /projects/{project_id}": "delete_project",
    "PATCH /projects/{project_id}": "update_project",
    "POST /projects/{project_id}/acts": "create_act",
    "PATCH /projects/{project_id}/acts/{act_id}": "update_act",
    "DELETE /projects/{project_id}/acts/{act_id}": "delete_act",
    "GET /projects/{project_id}/agent-proposals": "list_proposals",
    "POST /projects/{project_id}/agent-proposals": "propose_screenplay_change",
    "POST /projects/{project_id}/agent-proposals/{proposal_id}/approve": "review_screenplay_proposal",
    "POST /projects/{project_id}/agent-proposals/{proposal_id}/reject": "reject_proposal",
    "POST /projects/{project_id}/agent-proposals/{proposal_id}/rollback": "review_screenplay_proposal",
    "GET /projects/{project_id}/artifacts": "read_project_artifacts",
    "POST /projects/{project_id}/artifacts": "write_artifact",
    "PATCH /projects/{project_id}/artifacts/{artifact_id}": "write_artifact",
    "DELETE /projects/{project_id}/artifacts/{artifact_id}": "write_artifact",
    "POST /projects/{project_id}/artifacts/{artifact_id}/operations": "apply_story_operation",
    "POST /projects/{project_id}/artwork": EXEMPT + ": binary image upload from the browser",
    "POST /projects/{project_id}/backups": "create_project_backup",
    "GET /projects/{project_id}/backups": "list_project_backups",
    "GET /projects/{project_id}/backups/{filename}": EXEMPT + ": file download",
    "POST /projects/{project_id}/backups/{filename}/restore": "restore_project_backup",
    "GET /projects/{project_id}/beats": "list_story_entities",
    "POST /projects/{project_id}/beats": "create_story_entity",
    "PATCH /projects/{project_id}/beats/{beat_id}": "update_story_entity",
    "DELETE /projects/{project_id}/beats/{beat_id}": "delete_story_entity",
    "GET /projects/{project_id}/characters": "list_story_entities",
    "POST /projects/{project_id}/characters": "create_story_entity",
    "GET /projects/{project_id}/characters/{character_id}": "read_character",
    "PATCH /projects/{project_id}/characters/{character_id}": "update_story_entity",
    "DELETE /projects/{project_id}/characters/{character_id}": "delete_story_entity",
    "GET /projects/{project_id}/characters/{character_id}/timeline": "read_character",
    "GET /projects/{project_id}/context/workflows": "start_context_workflow",
    "POST /projects/{project_id}/context/workflows/runs": "start_context_workflow",
    "POST /projects/{project_id}/context/workflows/runs/{run_id}/apply": "apply_context_workflow",
    "GET /projects/{project_id}/copilot/messages": EXEMPT + ": the in-app chat transcript",
    "POST /projects/{project_id}/copilot/messages": EXEMPT + ": the in-app chat transcript",
    "POST /projects/{project_id}/copilot/messages/respond": EXEMPT + ": the in-app chat agent itself",
    "POST /projects/{project_id}/copilot/messages/respond-async": EXEMPT + ": the in-app chat agent itself",
    "POST /projects/{project_id}/duplicate": "duplicate_project",
    "GET /projects/{project_id}/evaluations": "read_project_evaluations",
    "POST /projects/{project_id}/evaluations": EXEMPT + ": evaluators write results, clients read them",
    "POST /projects/{project_id}/evaluations/runs": "start_evaluation",
    "GET /projects/{project_id}/events": EXEMPT + ": browser live-sync stream",
    "POST /projects/{project_id}/feedback": EXEMPT + ": the writer's thumbs on agent output",
    "GET /projects/{project_id}/insights": EXEMPT + ": the writer's usefulness dashboard",
    "GET /projects/{project_id}/knowledge-graph": "read_story_twin",
    "POST /projects/{project_id}/knowledge-graph/edges": "write_canon_edge",
    "DELETE /projects/{project_id}/knowledge-graph/edges/{edge_id}": "write_canon_edge",
    "POST /projects/{project_id}/knowledge-graph/nodes": "write_canon_node",
    "PATCH /projects/{project_id}/knowledge-graph/nodes/{node_id}": "write_canon_node",
    "DELETE /projects/{project_id}/knowledge-graph/nodes/{node_id}": "write_canon_node",
    "GET /projects/{project_id}/locations": "list_story_entities",
    "POST /projects/{project_id}/locations": "create_story_entity",
    "PATCH /projects/{project_id}/locations/{location_id}": "update_story_entity",
    "DELETE /projects/{project_id}/locations/{location_id}": "delete_story_entity",
    "GET /projects/{project_id}/mcp-approvals": EXEMPT + ": only the writer decides approvals",
    "POST /projects/{project_id}/mcp-approvals/{approval_id}/approve": EXEMPT + ": only the writer decides approvals",
    "POST /projects/{project_id}/mcp-approvals/{approval_id}/reject": EXEMPT + ": only the writer decides approvals",
    "GET /projects/{project_id}/moments": "list_story_entities",
    "POST /projects/{project_id}/moments": "create_story_entity",
    "PATCH /projects/{project_id}/moments/{moment_id}": "update_story_entity",
    "DELETE /projects/{project_id}/moments/{moment_id}": "delete_story_entity",
    "GET /projects/{project_id}/monty-executions": "read_monty_executions",
    "GET /projects/{project_id}/narrative-variants": "list_story_entities",
    "POST /projects/{project_id}/narrative-variants": "create_story_entity",
    "PATCH /projects/{project_id}/narrative-variants/{variant_id}": "update_story_entity",
    "DELETE /projects/{project_id}/narrative-variants/{variant_id}": "delete_story_entity",
    "POST /projects/{project_id}/rag/reindex": "reindex_project_search",
    "GET /projects/{project_id}/rag/search": "retrieve_project_context",
    "GET /projects/{project_id}/rag/stats": EXEMPT + ": operator diagnostics",
    "GET /projects/{project_id}/references": "read_project_overview",
    "PATCH /projects/{project_id}/references/{reference_id}": "write_reference",
    "DELETE /projects/{project_id}/references/{reference_id}": "write_reference",
    "GET /projects/{project_id}/relationships": "list_story_entities",
    "POST /projects/{project_id}/relationships": "create_story_entity",
    "PATCH /projects/{project_id}/relationships/{relationship_id}": "update_story_entity",
    "DELETE /projects/{project_id}/relationships/{relationship_id}": "delete_story_entity",
    "POST /projects/{project_id}/room/chat": EXEMPT + ": the in-app chat agent itself",
    "GET /projects/{project_id}/room/runs": "read_workflow_run",
    "GET /projects/{project_id}/room/threads": EXEMPT + ": the in-app chat's own threads",
    "GET /projects/{project_id}/room/threads/{thread_id}": EXEMPT + ": the in-app chat's own threads",
    "PATCH /projects/{project_id}/room/threads/{thread_id}": EXEMPT + ": the in-app chat's own threads",
    "DELETE /projects/{project_id}/room/threads/{thread_id}": EXEMPT + ": the in-app chat's own threads",
    "GET /projects/{project_id}/room/workflows": "list_room_workflows",
    "POST /projects/{project_id}/room/workflows": "start_room_workflow",
    "POST /projects/{project_id}/runs": "start_context_workflow",
    "GET /projects/{project_id}/runs": "read_workflow_run",
    "GET /projects/{project_id}/runs/{run_id}": "read_workflow_run",
    "POST /projects/{project_id}/runs/{run_id}/cancel": "control_workflow_run",
    "POST /projects/{project_id}/runs/{run_id}/resume": "control_workflow_run",
    "POST /projects/{project_id}/scenes": "create_scene",
    "DELETE /projects/{project_id}/scenes/{scene_id}": "delete_scene",
    "PATCH /projects/{project_id}/scenes/{scene_id}": "update_scene",
    "POST /projects/{project_id}/scenes/{scene_id}/blocks": "create_block",
    "PUT /projects/{project_id}/scenes/{scene_id}/blocks/order": "reorder_blocks",
    "PUT /projects/{project_id}/scenes/{scene_id}/content": "write_scene_content",
    "PATCH /projects/{project_id}/scenes/{scene_id}/blocks/{block_id}": "update_block",
    "DELETE /projects/{project_id}/scenes/{scene_id}/blocks/{block_id}": "delete_block",
    "GET /projects/{project_id}/scenes/{scene_id}/blocks/{block_id}/translations": "read_dialogue_translations",
    "PUT /projects/{project_id}/scenes/{scene_id}/blocks/{block_id}/translations/{language}": "propose_dialogue_translation",
    "POST /projects/{project_id}/scenes/{scene_id}/move": "move_scene",
    "GET /projects/{project_id}/scenes/{scene_id}/revisions": "read_scene_revisions",
    "POST /projects/{project_id}/scenes/{scene_id}/revisions": "snapshot_scene",
    "GET /projects/{project_id}/scenes/{scene_id}/revisions/{revision_id}/diff/{other_revision_id}": "diff_scene_revisions",
    "POST /projects/{project_id}/scenes/{scene_id}/revisions/{revision_id}/restore": "restore_scene_revision",
    "GET /projects/{project_id}/screenplays/{screenplay_id}/benchmark-manifest": EXEMPT + ": benchmark tooling",
    "GET /projects/{project_id}/screenplays/{screenplay_id}/exports/{file_format}": "render_screenplay_export",
    "POST /projects/{project_id}/screenplays/{screenplay_id}/imports/{file_format}": "import_screenplay",
    "POST /projects/{project_id}/screenplays/{screenplay_id}/scenes": "create_scene",
    "POST /projects/{project_id}/screenplays/{screenplay_id}/timeline/proposals": "propose_timeline_reorder",
    "GET /projects/{project_id}/screenplays/{screenplay_id}/timeline/proposals": "read_project_overview",
    "POST /projects/{project_id}/screenplays/{screenplay_id}/timeline/proposals/{proposal_id}/approve": "review_timeline_proposal",
    "POST /projects/{project_id}/screenplays/{screenplay_id}/timeline/proposals/{proposal_id}/reject": "reject_timeline_proposal",
    "POST /projects/{project_id}/screenplays/{screenplay_id}/timeline/proposals/{proposal_id}/rollback": "review_timeline_proposal",
    "GET /projects/{project_id}/storyline": "read_storyline",
    "GET /projects/{project_id}/timeline-events": "list_story_entities",
    "POST /projects/{project_id}/timeline-events": "create_story_entity",
    "PATCH /projects/{project_id}/timeline-events/{event_id}": "update_story_entity",
    "DELETE /projects/{project_id}/timeline-events/{event_id}": "delete_story_entity",
    "GET /projects/{project_id}/twin": "read_story_twin",
    "POST /projects/{project_id}/twin/refresh": "refresh_story_twin_now",
    "GET /projects/{project_id}/visuals": "read_story_visuals",
    "GET /projects/{project_id}/workspace": "read_screenplay_scenes",
    "GET /settings/providers": EXEMPT + ": provider secrets stay with the installation",
    "POST /settings/providers": EXEMPT + ": provider secrets stay with the installation",
    "GET /settings/providers/default/models": EXEMPT + ": provider configuration",
    "PATCH /settings/providers/{profile_id}": EXEMPT + ": provider secrets stay with the installation",
    "GET /settings/providers/{profile_id}/models": EXEMPT + ": provider configuration",
    "POST /settings/providers/{profile_id}/test": EXEMPT + ": provider configuration",
    "GET /writer/brief": "read_writer_twin",
    "GET /writer/memories": "read_writer_twin",
    "POST /writer/memories": "remember_writer_preference",
    "DELETE /writer/memories/{memory_id}": EXEMPT + ": forgetting is the writer's call",
    "GET /writer/profile": "read_writer_twin",
    "PUT /writer/profile": "update_writer_profile",
}


def test_every_rest_operation_has_an_mcp_tool_or_a_reason() -> None:
    """A new REST route must come with an MCP tool (or an explicit exemption) so external agents keep parity."""
    schema = create_app().openapi()
    operations = {f"{method.upper()} {path.removeprefix('/api/v1')}" for path, item in schema["paths"].items() for method in item}
    assert sorted(operations - set(PARITY)) == [], "map the new routes in PARITY"
    assert sorted(set(PARITY) - operations) == [], "drop removed routes from PARITY"
    tools = {tool.name for tool in run_async(server.mcp.list_tools())}
    missing = {target for target in PARITY.values() if not target.startswith(EXEMPT)} - tools
    assert missing == set()
    assert "greet" not in tools


@pytest.fixture
def studio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[AsyncSession]:
    """Route MCP calls to a fresh database where the stdio client is trusted installation-wide."""
    context = memory_session(f"sqlite+aiosqlite:///{tmp_path / 'mcp.db'}")
    session = run_async(context.__aenter__())

    async def seed() -> None:
        """Register the stdio client with every capability on every project."""
        client = MCPClient(client_id="mcp-stdio", name="Local agent")
        session.add(client)
        await session.flush()
        from draftpilot.core.capabilities import capability_catalog

        session.add_all([MCPGrant(client_id=client.id or 0, project_id=None, capability=item.name) for item in capability_catalog()])
        await session.commit()

    run_async(seed())

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        """Hand every tool the shared test session."""
        yield session

    for module in (server, studio_tools):
        monkeypatch.setattr(module, "session_scope", scope)
    monkeypatch.setattr("draftpilot.core.events.publish", _noop)
    monkeypatch.setattr("draftpilot.core.temporal.start_best_effort", _noop)
    yield session
    run_async(context.__aexit__(None, None, None))


async def _noop(*_args: object, **_kwargs: object) -> None:
    """Swallow side effects (Redis, Temporal)."""


class Studio:
    """Call MCP tools as an external client, approving gated writes as the writer would."""

    def __init__(self, client: Client, session: AsyncSession, meta: dict[str, Any] | None = None) -> None:
        """Wrap a connected client."""
        self.client, self.session, self.meta = client, session, meta
        self.approvals = 0

    async def call(self, tool: str, **arguments: Any) -> Any:
        """Call a tool; when it asks for writer approval, approve it and retry once."""
        try:
            return (await self.client.call_tool(tool, arguments, meta=self.meta)).structured_content
        except ToolError as exc:
            match = re.search(r"approval request (\d+) is pending", str(exc))
            if match is None:
                raise
            approval_id = int(match.group(1))
            project_id = arguments.get("project_id")
            assert isinstance(project_id, int)
            await decide_approval(self.session, project_id, approval_id, True)
            self.approvals += 1
            return (await self.client.call_tool(tool, {**arguments, "approval_id": approval_id}, meta=self.meta)).structured_content


def _result(value: Any) -> Any:
    """Unwrap FastMCP's ``{"result": ...}`` envelope for non-object returns."""
    return value["result"] if isinstance(value, dict) and set(value) == {"result"} else value


def test_an_external_agent_develops_a_screenplay_end_to_end(studio: AsyncSession) -> None:
    """Project → storyline → cast and timelines → outline → scenes → revisions → review, all over MCP."""

    async def scenario() -> None:
        """Drive the whole flow through tools."""
        async with Client(server.mcp) as client:
            dp = Studio(client, studio)
            project = await dp.call("create_project", title="The River", logline="A son retraces his father's tall tales.")
            pid = project["id"]
            assert dp.approvals == 0  # creating is not destructive
            assert [item["title"] for item in _result(await dp.call("list_projects"))] == ["The River"]
            updated = await dp.call("update_project", project_id=pid, fields={"premise": "Stories outlive us.", "tone": "Wistful"}, expected_version=project["version"])
            assert updated["premise"] == "Stories outlive us." and dp.approvals == 1
            edward = await dp.call("create_story_entity", project_id=pid, kind="character", fields={"name": "Edward", "role": "protagonist", "want": "Be a legend", "need": "Be known", "objective": "Win Sandra"})
            will = await dp.call("create_story_entity", project_id=pid, kind="character", fields={"name": "Will"})
            await dp.call("create_story_entity", project_id=pid, kind="relationship", fields={"source_character_id": edward["id"], "target_character_id": will["id"], "relation": "father of"})
            await dp.call("create_story_entity", project_id=pid, kind="timeline_event", fields={"character_id": edward["id"], "title": "Sees his death in the witch's eye", "story_time": "1937"})
            profile = await dp.call("read_character", project_id=pid, character_id=edward["id"])
            assert profile["timeline"][0]["story_time"] == "1937" and profile["relationships"][0]["relation"] == "father of"
            proposal = await dp.call("propose_outline", project_id=pid, beats=[{"act": 1, "title": "The witch"}, {"act": 2, "title": "Spectre"}, {"act": 3, "title": "The river"}])
            assert proposal["status"] == "proposed" and proposal["target_kind"] == "outline"
            pending = _result(await dp.call("list_proposals", project_id=pid))
            assert [item["id"] for item in pending] == [proposal["id"]]
            from draftpilot.core import proposals

            await proposals.approve(studio, pid, proposal["id"])  # the writer approves in the studio
            outline = await dp.call("read_outline", project_id=pid)
            assert [len(act["beats"]) for act in outline["acts"]] == [1, 1, 1]
            scene = await dp.call(
                "create_scene",
                project_id=pid,
                heading="EXT. RIVER - DAY",
                fountain="Edward wades in.\n\nEDWARD\nThe biggest fish in the river gets that way by never being caught.",
                act_id=outline["acts"][2]["id"],
            )
            beat = outline["acts"][2]["beats"][0]
            await dp.call("update_story_entity", project_id=pid, kind="beat", entity_id=beat["id"], fields={"scene_ids": [scene["id"]], "status": "drafted"}, expected_version=beat["version"])
            revision = await dp.call("snapshot_scene", project_id=pid, scene_id=scene["id"], message="first pass")
            written = await dp.call("write_scene", project_id=pid, scene_id=scene["id"], fountain="EXT. RIVER - NIGHT\n\nThe water is black.", expected_version=scene["version"])
            assert written["heading"] == "EXT. RIVER - NIGHT"
            second = await dp.call("snapshot_scene", project_id=pid, scene_id=scene["id"], message="second pass")
            diff = await dp.call("diff_scene_revisions", project_id=pid, scene_id=scene["id"], revision_id=revision["id"], other_revision_id=second["id"])
            assert "NIGHT" in diff["diff"]
            restored = await dp.call("restore_scene_revision", project_id=pid, scene_id=scene["id"], revision_id=revision["id"], expected_version=written["version"])
            assert restored["heading"] == "EXT. RIVER - DAY"
            imported = await dp.call("import_screenplay", project_id=pid, file_format="fountain", content="INT. HOUSE - DAY\n\nRain.\n")
            assert imported["title"].endswith("(Imported)")
            node = await dp.call("write_canon_node", project_id=pid, kind="motif", label="Water", description="Rivers, rain, fish.")
            artifact = await dp.call("write_artifact", project_id=pid, kind="notes", title="Research", content="Alabama, 1940s.")
            assert node["label"] == "Water" and artifact["title"] == "Research"
            context = await dp.call("read_story_context", project_id=pid)
            assert "Logline: A son retraces" in context["story"] and "want: Be a legend" in context["story"] and "The witch" in context["story"]
            idea = await dp.call("propose_story_change", project_id=pid, kind="location", action="create", fields={"name": "Spectre"})
            rejected = await dp.call("reject_proposal", project_id=pid, proposal_id=idea["id"])
            assert rejected["status"] == "rejected"
            await dp.call("delete_scene", project_id=pid, scene_id=scene["id"], expected_version=restored["version"])
            assert (await dp.call("read_outline", project_id=pid))["acts"][2]["scenes"] == []
            prompts = {prompt.name for prompt in await client.list_prompts()}
            assert {"develop_storyline", "develop_characters", "build_outline", "draft_script", "review_script"} <= prompts
            characters = await client.read_resource(f"draftpilot://projects/{pid}/characters")
            assert "Edward" in str(characters)

    run_async(scenario())


def test_an_external_agent_saves_a_scene_in_one_batched_write(studio: AsyncSession) -> None:
    """``write_scene_content`` mirrors the REST content route: one approval, one version bump, agent origin."""

    async def scenario() -> None:
        """Create a scene, then rewrite its blocks through the batched tool."""
        from draftpilot.core.screenplay.hydrate import blocks_for_scene

        async with Client(server.mcp) as client:
            dp = Studio(client, studio)
            pid = (await dp.call("create_project", title="The River"))["id"]
            scene = await dp.call("create_scene", project_id=pid, heading="EXT. RIVER - DAY", fountain="Edward wades in.\n\nEDWARD\nThe fish waits.")
            first, *_, second = await blocks_for_scene(studio, scene["id"])
            result = await dp.call(
                "write_scene_content",
                project_id=pid,
                scene_id=scene["id"],
                heading="EXT. RIVER - NIGHT",
                blocks=[{"id": second.id, "text": "The fish waits, patient."}, {"element_type": "transition", "text": "CUT TO:"}],
                expected_version=scene["version"],
            )
            assert result["version"] == scene["version"] + 1 and len(result["created_ids"]) == 1
            assert result["block_ids"] == [second.id, result["created_ids"][0]]
            blocks = await blocks_for_scene(studio, scene["id"])
            assert [(block.text, block.origin) for block in blocks] == [("The fish waits, patient.", "agent"), ("CUT TO:", "agent")]
            assert first.id not in {block.id for block in blocks}

    run_async(scenario())


def test_an_external_agent_maps_a_shared_moment(studio: AsyncSession) -> None:
    """Moments, the new event fields and variants work over MCP; agents may propose moments but not variants."""

    async def scenario() -> None:
        """Create a moment, link two characters' events to it, then propose another moment."""
        async with Client(server.mcp) as client:
            dp = Studio(client, studio)
            pid = (await dp.call("create_project", title="The River"))["id"]
            scene = await dp.call("create_scene", project_id=pid, heading="EXT. RIVER - DAY", fountain="Edward wades in.")
            edward = await dp.call("create_story_entity", project_id=pid, kind="character", fields={"name": "Edward"})
            will = await dp.call("create_story_entity", project_id=pid, kind="character", fields={"name": "Will"})
            moment = await dp.call("create_story_entity", project_id=pid, kind="moment", fields={"title": "The river", "chrono_index": 3, "scene_id": scene["id"]})
            for character, intensity in ((edward, 5), (will, -4)):
                fields = {"character_id": character["id"], "title": "At the river", "intensity": intensity, "motivation": "Love", "moment_id": moment["id"]}
                await dp.call("create_story_entity", project_id=pid, kind="timeline_event", fields=fields)
            lanes = _result(await dp.call("list_story_entities", project_id=pid, kind="timeline_event", moment_id=moment["id"]))
            assert sorted(item["intensity"] for item in lanes) == [-4, 5]
            visuals = await dp.call("read_story_visuals", project_id=pid)
            assert [(item["id"], item["intensity"], item["event_count"]) for item in visuals["scenes"]] == [(scene["id"], 0.5, 2)]
            assert [(edge["shared_moments"], edge["shared_scenes"]) for edge in visuals["edges"]] == [(1, 1)]
            edited = await dp.call("update_story_entity", project_id=pid, kind="moment", entity_id=moment["id"], fields={"story_time": "1987"}, expected_version=1)
            assert edited["version"] == 2
            variant = await dp.call("create_story_entity", project_id=pid, kind="variant", fields={"name": "As shot", "scene_ids": [scene["id"]]})
            assert _result(await dp.call("list_story_entities", project_id=pid, kind="variant"))[0]["id"] == variant["id"]
            proposal = await dp.call("propose_story_change", project_id=pid, kind="moment", action="create", fields={"title": "The funeral"})
            assert proposal["target_kind"] == "moment" and proposal["status"] == "proposed"
            with pytest.raises(ToolError):
                await dp.call("propose_story_change", project_id=pid, kind="variant", action="create", fields={"name": "Mine"})
            await dp.call("delete_story_entity", project_id=pid, kind="moment", entity_id=moment["id"], expected_version=2)
            assert _result(await dp.call("list_story_entities", project_id=pid, kind="moment")) == []

    run_async(scenario())


def test_grants_and_project_scope_are_enforced(studio: AsyncSession) -> None:
    """Without grants nothing works; an in-app agent stays inside its project and needs approval to write."""

    async def scenario() -> None:
        """Create two projects, then call as an untrusted client and as an in-app agent."""
        async with Client(server.mcp) as client:
            dp = Studio(client, studio)
            first = await dp.call("create_project", title="Mine")
            second = await dp.call("create_project", title="Theirs")
            room = Studio(client, studio, identity_meta(InternalAgent(project_id=first["id"], role="story_editor")))
            assert (await room.call("read_storyline", project_id=first["id"]))["title"] == "Mine"
            with pytest.raises(ToolError, match="not granted"):
                await room.client.call_tool("read_storyline", {"project_id": second["id"]}, meta=room.meta)
            with pytest.raises(ToolError, match="approval request"):
                await room.client.call_tool(
                    "create_story_entity", {"project_id": first["id"], "kind": "character", "fields": {"name": "X"}}, meta=room.meta
                )
            proposal = await room.call("propose_story_change", project_id=first["id"], kind="character", action="create", fields={"name": "X"})
            assert proposal["status"] == "proposed"
            with pytest.raises(ToolError, match="not granted"):
                await room.client.call_tool("create_project", {"title": "Escape"}, meta=room.meta)
        from sqlmodel import delete

        await studio.exec(delete(MCPGrant))  # type: ignore[call-overload]
        await studio.commit()
        async with Client(server.mcp) as client:
            with pytest.raises(ToolError, match="not granted"):
                await client.call_tool("read_storyline", {"project_id": first["id"]})
            with pytest.raises(ToolError, match="not granted"):
                await client.call_tool("create_project", {"title": "Nope"})
            assert _result((await client.call_tool("list_projects", {})).structured_content) == []

    run_async(scenario())
