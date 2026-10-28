"""Studio tools: the full screenplay-development surface over MCP.

Everything a writer can do in the studio is here, for in-app agents and external clients alike:
projects, storyline, characters and their timelines and relationships, locations, the outline
(acts and beats), scenes and blocks, revisions, imports, proposals, the canon graph, artifacts
and the Writer twin. Every call is authorized per client and project and audited; writes that
change the writer's work need a writer-decided ``approval_id`` (or go through ``propose_*``,
which queues a reviewable proposal instead).
"""

import base64
import binascii
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastmcp import Context
from fastmcp.exceptions import ToolError
from pydantic import Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import proposals, studio, timeline_proposals
from draftpilot.core.config import settings
from draftpilot.core.db import session_scope
from draftpilot.core.errors import DomainError
from draftpilot.core.scene_proposals import apply_scene_rewrite, parse_scene_fountain
from draftpilot.core.scene_sync import scene_changed
from draftpilot.core.story import entities, storyline, structure, visuals
from draftpilot.core.story.proposals import propose_outline as queue_outline
from draftpilot.core.story.proposals import propose_story_change as queue_story_change
from draftpilot.core.twins import (
    get_writer_profile,
    refresh_story_twin,
    story_twin_brief,
    writer_twin_brief,
)
from draftpilot.crud import agent_proposals as proposals_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud.mcp_access import authorize_invocation, list_grants
from draftpilot.mcp.server import _client_id, mcp
from draftpilot.models import (
    ActRead,
    AgentProposalRead,
    BlockRead,
    BlockType,
    ProjectCreate,
    ProjectRead,
    ReferenceKind,
    SceneRead,
    SceneRevisionRead,
    SceneUpdate,
    ScreenplayRead,
    StoryArtifactRead,
    WriterMemory,
)

EntityKind = Literal["character", "relationship", "timeline_event", "location", "beat", "moment", "variant"]
ProposalKind = Literal["character", "relationship", "timeline_event", "location", "beat", "moment", "storyline"]
READ = {"read_only_hint": True}
WRITE = {"destructive_hint": False}
DESTRUCTIVE = {"destructive_hint": True}


@asynccontextmanager
async def authorized(
    ctx: Context,
    project_id: int | None,
    capability: str,
    action: str,
    summary: Mapping[str, Any] | None = None,
    *,
    approval_id: int | None = None,
    arguments: Mapping[str, Any] | None = None,
) -> AsyncIterator[AsyncSession]:
    """Authorize and audit one call, then yield a session; domain errors become tool errors."""
    async with session_scope() as session:
        try:
            await authorize_invocation(
                session,
                _client_id(ctx),
                project_id,
                capability,
                action,
                dict(summary or {}),
                approval_id=approval_id,
                arguments=dict(arguments) if arguments is not None else None,
            )
        except PermissionError as exc:
            raise ToolError(str(exc)) from exc
        try:
            yield session
        except DomainError as exc:
            await session.rollback()
            raise ToolError(str(exc.detail)) from exc


def _bounded(result: Any) -> Any:
    """Refuse results larger than the configured MCP output limit."""
    if len(json.dumps(result, default=str)) > settings.mcp.max_output_chars:
        raise ToolError("Result exceeds the MCP output limit; narrow the request")
    return result


def _dump(schema: Any, row: Any) -> dict[str, Any]:
    """Serialise a row through a read schema."""
    data: dict[str, Any] = schema.model_validate(row, from_attributes=True).model_dump(mode="json")
    return data


def _entity(kind: str, row: Any) -> dict[str, Any]:
    """Serialise a story entity."""
    return entities.to_read(entities.entity_kind(kind), row)


# --- projects -----------------------------------------------------------------------------------


@mcp.tool(annotations=READ, tags={"projects"})
async def list_projects(ctx: Context) -> list[dict[str, object]]:
    """List the projects you can work on (id, title, logline, version)."""
    client_id = _client_id(ctx)
    async with session_scope() as session:
        projects = await projects_crud.list_all(session)
        installation = {grant.capability for grant in await list_grants(session, None, client_id)}
        visible: list[dict[str, object]] = []
        for project in projects:
            if "projects.read" in installation or await list_grants(session, project.id, client_id):
                visible.append({"id": project.id, "title": project.title, "logline": project.logline, "version": project.version})
        try:
            await authorize_invocation(session, client_id, None, "projects.read", "list", {})
        except PermissionError:
            # Without installation access, a client still sees the projects it holds grants on.
            pass
    return visible


@mcp.tool(annotations=WRITE, tags={"projects"})
async def create_project(
    title: Annotated[str, Field(min_length=1, max_length=200)],
    ctx: Context,
    logline: str | None = None,
    premise: str | None = None,
    genres: list[str] | None = None,
    description: str | None = None,
    primary_language: str = "English",
) -> dict[str, object]:
    """Start a new project; it gets a feature draft with Act One, ready for scenes."""
    async with authorized(ctx, None, "projects.create", "create", {"title": title}) as session:
        project = await studio.create_project(
            session,
            ProjectCreate(
                title=title, logline=logline, premise=premise, genres=genres or [], description=description, primary_language=primary_language
            ),
        )
    return _dump(ProjectRead, project)


@mcp.tool(annotations=WRITE, tags={"projects", "story"})
async def update_project(
    project_id: int,
    fields: dict[str, Any],
    expected_version: int,
    ctx: Context,
    approval_id: int | None = None,
) -> dict[str, object]:
    """Edit project fields: title, logline, premise, synopsis, theme, tone, description, story_outline, genres, visual_style, ..."""
    arguments = {"project_id": project_id, "fields": fields, "expected_version": expected_version}
    async with authorized(ctx, project_id, "projects.update", "update", {"fields": sorted(fields)}, approval_id=approval_id, arguments=arguments) as session:
        project = await storyline.update_project(session, project_id, fields, expected_version)
    return _dump(ProjectRead, project)


@mcp.tool(annotations=WRITE, tags={"projects"})
async def duplicate_project(project_id: int, ctx: Context, title: str | None = None) -> dict[str, object]:
    """Copy a project (brief, story, artifacts, every draft) into a new project."""
    async with authorized(ctx, project_id, "projects.duplicate", "duplicate", {}) as session:
        project = await studio.duplicate_project(session, project_id, title)
    return _dump(ProjectRead, project)


@mcp.tool(annotations=DESTRUCTIVE, tags={"projects"})
async def delete_project(project_id: int, ctx: Context, approval_id: int | None = None) -> dict[str, object]:
    """Back up and delete a project; it can be restored from the backup."""
    async with authorized(ctx, project_id, "projects.delete", "delete", {}, approval_id=approval_id, arguments={"project_id": project_id}) as session:
        return await studio.delete_project(session, project_id)


# --- story: reads -------------------------------------------------------------------------------


@mcp.tool(annotations=READ, tags={"story"})
async def read_storyline(project_id: int, ctx: Context) -> dict[str, object]:
    """Read the storyline: title, logline, premise, synopsis, theme, tone, description and outline text."""
    async with authorized(ctx, project_id, "story.read", "read") as session:
        return storyline.storyline(await structure.require_project(session, project_id))


@mcp.tool(annotations=READ, tags={"story"})
async def list_story_entities(
    project_id: int, kind: EntityKind, ctx: Context, character_id: int | None = None, moment_id: int | None = None
) -> list[dict[str, object]]:
    """List characters, relationships, timeline events (one character's, or one moment's participants), locations, beats, shared moments or narrative variants."""
    async with authorized(ctx, project_id, "story.read", "read", {"kind": kind}) as session:
        rows = await entities.list_entities(session, project_id, kind, character_id=character_id, moment_id=moment_id)
        return _bounded([_entity(kind, row) for row in rows])


@mcp.tool(annotations=READ, tags={"story"})
async def read_character(project_id: int, character_id: int, ctx: Context) -> dict[str, object]:
    """Read one character's full profile with their timeline and relationships."""
    async with authorized(ctx, project_id, "story.read", "read", {"character_id": character_id}) as session:
        row = await entities.get_entity(session, project_id, "character", character_id)
        timeline = await entities.list_entities(session, project_id, "timeline_event", character_id=character_id)
        relations = await entities.list_entities(session, project_id, "relationship", character_id=character_id)
        return _bounded(
            {
                **_entity("character", row),
                "timeline": [_entity("timeline_event", item) for item in timeline],
                "relationships": [_entity("relationship", item) for item in relations],
            }
        )


@mcp.tool(annotations=READ, tags={"story", "structure"})
async def read_outline(project_id: int, ctx: Context, screenplay_id: int | None = None) -> dict[str, object]:
    """Read the outline: acts in order, each with its beats and the scenes in it (headings only)."""
    async with authorized(ctx, project_id, "story.read", "read") as session:
        acts = await structure.acts_for_project(session, project_id, screenplay_id)
        scenes = await structure.scenes_for_project(session, project_id, screenplay_id)
        beats = await entities.list_entities(session, project_id, "beat")
        act_ids = {act.id for act in acts}
        result = {
            "acts": [
                {
                    **_dump(ActRead, act),
                    "beats": [_entity("beat", beat) for beat in beats if beat.act_id == act.id],
                    "scenes": [{"id": scene.id, "heading": scene.heading, "version": scene.version} for scene in scenes if scene.act_id == act.id],
                }
                for act in acts
            ],
            "unplaced_beats": [_entity("beat", beat) for beat in beats if beat.act_id not in act_ids],
        }
        return _bounded(result)


@mcp.tool(annotations=READ, tags={"story", "structure"})
async def read_story_visuals(project_id: int, ctx: Context, screenplay_id: int | None = None) -> dict[str, object]:
    """Read what the visual tools draw: scenes with runtime and cast-average intensity, beat milestones and the cast graph."""
    async with authorized(ctx, project_id, "story.read", "read") as session:
        return _bounded((await visuals.story_visuals(session, project_id, screenplay_id)).model_dump(mode="json"))


@mcp.tool(annotations=READ, tags={"story"})
async def read_story_context(project_id: int, ctx: Context) -> dict[str, str]:
    """Read the compact story brief every DraftPilot agent receives (storyline, cast, places, beats, canon) and the Writer twin brief."""
    async with authorized(ctx, project_id, "story.read", "read") as session:
        return {"story": await story_twin_brief(session, project_id), "writer": await writer_twin_brief(session, project_id)}


# --- story: writes -------------------------------------------------------------------------------


@mcp.tool(annotations=WRITE, tags={"story"})
async def create_story_entity(
    project_id: int, kind: EntityKind, fields: dict[str, Any], ctx: Context, approval_id: int | None = None
) -> dict[str, object]:
    """Create a character, relationship, timeline event, location, beat, shared moment or narrative variant (fields as in list_story_entities)."""
    arguments = {"project_id": project_id, "kind": kind, "fields": fields}
    async with authorized(ctx, project_id, "story.write", "create", {"kind": kind}, approval_id=approval_id, arguments=arguments) as session:
        return _entity(kind, await entities.create_entity(session, project_id, kind, fields, source="agent"))


@mcp.tool(annotations=WRITE, tags={"story"})
async def update_story_entity(
    project_id: int, kind: EntityKind, entity_id: int, fields: dict[str, Any], expected_version: int, ctx: Context, approval_id: int | None = None
) -> dict[str, object]:
    """Edit a story entity's fields when ``expected_version`` is still current."""
    arguments = {"project_id": project_id, "kind": kind, "entity_id": entity_id, "fields": fields, "expected_version": expected_version}
    async with authorized(ctx, project_id, "story.write", "update", {"kind": kind, "entity_id": entity_id}, approval_id=approval_id, arguments=arguments) as session:
        row = await entities.update_entity(session, project_id, kind, entity_id, fields, expected_version=expected_version, source="agent")
        return _entity(kind, row)


@mcp.tool(annotations=DESTRUCTIVE, tags={"story"})
async def delete_story_entity(
    project_id: int, kind: EntityKind, entity_id: int, expected_version: int, ctx: Context, approval_id: int | None = None
) -> dict[str, object]:
    """Delete a story entity (a character's timeline and relationships go with them)."""
    arguments = {"project_id": project_id, "kind": kind, "entity_id": entity_id, "expected_version": expected_version}
    async with authorized(ctx, project_id, "story.write", "delete", {"kind": kind, "entity_id": entity_id}, approval_id=approval_id, arguments=arguments) as session:
        return await entities.delete_entity(session, project_id, kind, entity_id, expected_version=expected_version)


@mcp.tool(annotations=WRITE, tags={"story", "proposals"})
async def propose_story_change(
    project_id: int,
    kind: ProposalKind,
    action: Literal["create", "update", "delete"],
    ctx: Context,
    fields: dict[str, Any] | None = None,
    entity_id: int | None = None,
    summary: str = "",
) -> dict[str, object]:
    """Queue a story change for the writer to approve: create/update/delete an entity (a shared moment too), or update the storyline."""
    async with authorized(ctx, project_id, "story.propose", "propose", {"kind": kind, "action": action}) as session:
        proposal = await queue_story_change(session, project_id, kind, action, fields, entity_id=entity_id, summary=summary)
        return _dump(AgentProposalRead, proposal)


@mcp.tool(annotations=WRITE, tags={"story", "proposals"})
async def propose_outline(project_id: int, beats: list[dict[str, Any]], ctx: Context, summary: str = "") -> dict[str, object]:
    """Queue a whole outline for approval; each beat is {act (1-based), title, summary, beat_type?}. Approving replaces the beats."""
    async with authorized(ctx, project_id, "story.propose", "propose", {"beats": len(beats)}) as session:
        return _dump(AgentProposalRead, await queue_outline(session, project_id, beats, summary=summary))


# --- structure ----------------------------------------------------------------------------------


@mcp.tool(annotations=WRITE, tags={"structure"})
async def create_act(project_id: int, title: str, ctx: Context, position: int | None = None, screenplay_id: int | None = None, approval_id: int | None = None) -> dict[str, object]:
    """Add an act to a draft (default: the first draft, at the end)."""
    arguments = {"project_id": project_id, "title": title, "position": position, "screenplay_id": screenplay_id}
    async with authorized(ctx, project_id, "structure.write", "create_act", {"title": title}, approval_id=approval_id, arguments=arguments) as session:
        return _dump(ActRead, await structure.create_act(session, project_id, screenplay_id, title, position))


@mcp.tool(annotations=WRITE, tags={"structure"})
async def update_act(project_id: int, act_id: int, ctx: Context, title: str | None = None, position: int | None = None, approval_id: int | None = None) -> dict[str, object]:
    """Rename or move an act."""
    arguments = {"project_id": project_id, "act_id": act_id, "title": title, "position": position}
    async with authorized(ctx, project_id, "structure.write", "update_act", {"act_id": act_id}, approval_id=approval_id, arguments=arguments) as session:
        return _dump(ActRead, await structure.update_act(session, project_id, act_id, title, position))


@mcp.tool(annotations=DESTRUCTIVE, tags={"structure"})
async def delete_act(project_id: int, act_id: int, ctx: Context, move_scenes_to: int | None = None, approval_id: int | None = None) -> dict[str, object]:
    """Delete an act; its scenes move to ``move_scenes_to`` (required when it has scenes)."""
    arguments = {"project_id": project_id, "act_id": act_id, "move_scenes_to": move_scenes_to}
    async with authorized(ctx, project_id, "structure.write", "delete_act", {"act_id": act_id}, approval_id=approval_id, arguments=arguments) as session:
        await structure.delete_act(session, project_id, act_id, move_scenes_to)
    return {"deleted_act_id": act_id}


@mcp.tool(annotations=WRITE, tags={"structure", "screenplay"})
async def create_scene(
    project_id: int,
    heading: str,
    ctx: Context,
    fountain: str | None = None,
    act_id: int | None = None,
    position: int | None = None,
    screenplay_id: int | None = None,
    approval_id: int | None = None,
) -> dict[str, object]:
    """Write a new scene: a heading plus, optionally, its body in Fountain (default: appended to the last act)."""
    arguments = {"project_id": project_id, "heading": heading, "fountain": fountain, "act_id": act_id, "position": position, "screenplay_id": screenplay_id}
    async with authorized(ctx, project_id, "structure.write", "create_scene", {"heading": heading}, approval_id=approval_id, arguments=arguments) as session:
        blocks: list[dict[str, Any]] = []
        if fountain and fountain.strip():
            starts_with_heading = fountain.lstrip().upper().startswith(("INT", "EXT", "I/E", "EST"))
            try:
                doc = parse_scene_fountain(fountain if starts_with_heading else f"{heading}\n\n{fountain}")
            except ValueError as exc:
                raise ToolError(str(exc)) from exc
            heading = doc.heading or heading
            blocks = [block.model_dump(mode="json", exclude={"id", "origin"}) for block in doc.blocks]
        scene = await structure.create_scene(
            session, project_id, heading, act_id=act_id, position=position, screenplay_id=screenplay_id, blocks=blocks, origin="agent"
        )
        return _dump(SceneRead, scene)


@mcp.tool(annotations=WRITE, tags={"structure", "screenplay"})
async def write_scene(
    project_id: int, scene_id: int, fountain: str, expected_version: int, ctx: Context, approval_id: int | None = None
) -> dict[str, object]:
    """Replace a scene's heading and body with Fountain text (block ids are kept where lines survive)."""
    arguments = {"project_id": project_id, "scene_id": scene_id, "fountain": fountain, "expected_version": expected_version}
    async with authorized(ctx, project_id, "structure.write", "write_scene", {"scene_id": scene_id}, approval_id=approval_id, arguments=arguments) as session:
        scene = await structure.versioned_scene(session, project_id, scene_id, expected_version)
        try:
            doc = parse_scene_fountain(fountain)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        await apply_scene_rewrite(
            session, scene, doc.heading or None, [block.model_dump(mode="json", exclude={"id", "origin"}) for block in doc.blocks], "agent"
        )
        await scene_changed(session, project_id, scene, reason="scene.written")
        return _dump(SceneRead, scene)


@mcp.tool(annotations=WRITE, tags={"structure", "screenplay"})
async def write_scene_content(
    project_id: int,
    scene_id: int,
    blocks: list[structure.SceneContentBlock],
    expected_version: int,
    ctx: Context,
    heading: str | None = None,
    approval_id: int | None = None,
) -> dict[str, object]:
    """Save a scene's blocks in one write: blocks with an ``id`` are updated, without one created, missing ones deleted."""
    arguments = {
        "project_id": project_id,
        "scene_id": scene_id,
        "blocks": [block.model_dump(mode="json", exclude_unset=True) for block in blocks],
        "expected_version": expected_version,
        "heading": heading,
    }
    content = structure.SceneContent(heading=heading, blocks=blocks)
    async with authorized(ctx, project_id, "structure.write", "write_scene_content", {"scene_id": scene_id}, approval_id=approval_id, arguments=arguments) as session:
        result = await structure.write_scene_content(session, project_id, scene_id, content, expected_version, origin="agent")
        return result.model_dump()


@mcp.tool(annotations=WRITE, tags={"structure"})
async def update_scene(
    project_id: int, scene_id: int, expected_version: int, ctx: Context, heading: str | None = None, scene_instruction: str | None = None, approval_id: int | None = None
) -> dict[str, object]:
    """Change a scene's heading or its standing instruction for agents."""
    arguments = {"project_id": project_id, "scene_id": scene_id, "expected_version": expected_version, "heading": heading, "scene_instruction": scene_instruction}
    changes = SceneUpdate.model_validate(
        {key: value for key, value in (("heading", heading), ("scene_instruction", scene_instruction)) if value is not None}
    )
    async with authorized(ctx, project_id, "structure.write", "update_scene", {"scene_id": scene_id}, approval_id=approval_id, arguments=arguments) as session:
        return _dump(SceneRead, await structure.update_scene(session, project_id, scene_id, changes, expected_version))


@mcp.tool(annotations=WRITE, tags={"structure"})
async def move_scene(
    project_id: int, scene_id: int, position: int, expected_version: int, ctx: Context, act_id: int | None = None, approval_id: int | None = None
) -> dict[str, object]:
    """Move a scene within its act or into another act of the same draft."""
    arguments = {"project_id": project_id, "scene_id": scene_id, "position": position, "expected_version": expected_version, "act_id": act_id}
    async with authorized(ctx, project_id, "structure.write", "move_scene", {"scene_id": scene_id}, approval_id=approval_id, arguments=arguments) as session:
        return _dump(SceneRead, await structure.move_scene(session, project_id, scene_id, position, expected_version, act_id=act_id))


@mcp.tool(annotations=DESTRUCTIVE, tags={"structure"})
async def delete_scene(project_id: int, scene_id: int, expected_version: int, ctx: Context, approval_id: int | None = None) -> dict[str, object]:
    """Delete a scene with its blocks (snapshot it first if you may want it back)."""
    arguments = {"project_id": project_id, "scene_id": scene_id, "expected_version": expected_version}
    async with authorized(ctx, project_id, "structure.write", "delete_scene", {"scene_id": scene_id}, approval_id=approval_id, arguments=arguments) as session:
        return await structure.delete_scene(session, project_id, scene_id, expected_version)


@mcp.tool(annotations=WRITE, tags={"structure", "screenplay"})
async def create_block(
    project_id: int,
    scene_id: int,
    element_type: Literal["action", "character", "dialogue", "parenthetical", "transition", "lyric", "note", "section", "synopsis", "shot", "page_break"],
    text: str,
    expected_version: int,
    ctx: Context,
    position: int | None = None,
    approval_id: int | None = None,
) -> dict[str, object]:
    """Insert one screenplay element into a scene (default: at the end)."""
    arguments = {"project_id": project_id, "scene_id": scene_id, "element_type": element_type, "text": text, "expected_version": expected_version, "position": position}
    async with authorized(ctx, project_id, "structure.write", "create_block", {"scene_id": scene_id}, approval_id=approval_id, arguments=arguments) as session:
        block = await structure.create_block(
            session, project_id, scene_id, {"element_type": element_type, "text": text}, expected_version, position=position, origin="agent"
        )
        return _dump(BlockRead, block)


@mcp.tool(annotations=WRITE, tags={"structure", "screenplay"})
async def update_block(
    project_id: int,
    scene_id: int,
    block_id: int,
    expected_version: int,
    ctx: Context,
    text: str | None = None,
    element_type: str | None = None,
    approval_id: int | None = None,
) -> dict[str, object]:
    """Edit one block's text or element type (``expected_version`` is the scene's version)."""
    from draftpilot.models import BlockUpdate

    arguments = {"project_id": project_id, "scene_id": scene_id, "block_id": block_id, "expected_version": expected_version, "text": text, "element_type": element_type}
    try:
        changes = BlockUpdate.model_validate(
            {key: value for key, value in (("text", text), ("element_type", BlockType(element_type) if element_type else None)) if value is not None}
        )
    except ValueError as exc:
        raise ToolError(f"Unknown element type {element_type!r}") from exc
    async with authorized(ctx, project_id, "structure.write", "update_block", {"block_id": block_id}, approval_id=approval_id, arguments=arguments) as session:
        return _dump(BlockRead, await structure.update_block(session, project_id, scene_id, block_id, changes, expected_version))


@mcp.tool(annotations=DESTRUCTIVE, tags={"structure", "screenplay"})
async def delete_block(project_id: int, scene_id: int, block_id: int, expected_version: int, ctx: Context, approval_id: int | None = None) -> dict[str, object]:
    """Delete one block from a scene."""
    arguments = {"project_id": project_id, "scene_id": scene_id, "block_id": block_id, "expected_version": expected_version}
    async with authorized(ctx, project_id, "structure.write", "delete_block", {"block_id": block_id}, approval_id=approval_id, arguments=arguments) as session:
        await structure.delete_block(session, project_id, scene_id, block_id, expected_version)
    return {"deleted_block_id": block_id}


@mcp.tool(annotations=WRITE, tags={"structure", "screenplay"})
async def reorder_blocks(project_id: int, scene_id: int, block_ids: list[int], expected_version: int, ctx: Context, approval_id: int | None = None) -> list[dict[str, object]]:
    """Put a scene's blocks in a new order (list every block id exactly once)."""
    arguments = {"project_id": project_id, "scene_id": scene_id, "block_ids": block_ids, "expected_version": expected_version}
    async with authorized(ctx, project_id, "structure.write", "reorder_blocks", {"scene_id": scene_id}, approval_id=approval_id, arguments=arguments) as session:
        return [_dump(BlockRead, block) for block in await structure.reorder_blocks(session, project_id, scene_id, block_ids, expected_version)]


# --- revisions and import -----------------------------------------------------------------------


@mcp.tool(annotations=WRITE, tags={"revisions"})
async def snapshot_scene(project_id: int, scene_id: int, ctx: Context, message: str | None = None) -> dict[str, object]:
    """Capture a named snapshot of a scene you can diff against or restore later."""
    async with authorized(ctx, project_id, "revisions.create", "snapshot", {"scene_id": scene_id}) as session:
        return _dump(SceneRevisionRead, await studio.snapshot_scene(session, project_id, scene_id, message))


@mcp.tool(annotations=DESTRUCTIVE, tags={"revisions"})
async def restore_scene_revision(
    project_id: int,
    scene_id: int,
    revision_id: int,
    expected_version: int,
    ctx: Context,
    sections: list[Literal["heading", "blocks"]] | None = None,
    approval_id: int | None = None,
) -> dict[str, object]:
    """Restore a scene's heading and/or blocks from a revision."""
    arguments = {"project_id": project_id, "scene_id": scene_id, "revision_id": revision_id, "expected_version": expected_version, "sections": sections}
    async with authorized(ctx, project_id, "revisions.restore", "restore", {"scene_id": scene_id}, approval_id=approval_id, arguments=arguments) as session:
        scene = await studio.restore_revision(session, project_id, scene_id, revision_id, expected_version, set(sections) if sections else None)
        return _dump(SceneRead, scene)


@mcp.tool(annotations=READ, tags={"revisions"})
async def diff_scene_revisions(project_id: int, scene_id: int, revision_id: int, other_revision_id: int, ctx: Context) -> dict[str, object]:
    """Show a unified diff between two revisions of a scene."""
    async with authorized(ctx, project_id, "revisions.read", "diff", {"scene_id": scene_id}) as session:
        return await studio.diff_revisions(session, project_id, scene_id, revision_id, other_revision_id)


@mcp.tool(annotations=WRITE, tags={"import"})
async def import_screenplay(
    project_id: int,
    file_format: Literal["fountain", "fdx", "pdf"],
    content: str,
    ctx: Context,
    base64_encoded: bool = False,
    title: str | None = None,
) -> dict[str, object]:
    """Import a script as a new draft of the project (Fountain/FDX as text; PDF base64-encoded)."""
    try:
        raw = base64.b64decode(content, validate=True) if base64_encoded or file_format == "pdf" else content.encode()
    except (binascii.Error, ValueError) as exc:
        raise ToolError("content is not valid base64") from exc
    async with authorized(ctx, project_id, "imports.create", "import", {"format": file_format, "bytes": len(raw)}) as session:
        return _dump(ScreenplayRead, await studio.import_screenplay(session, project_id, file_format, raw, title=title))


# --- proposals ----------------------------------------------------------------------------------


@mcp.tool(annotations=READ, tags={"proposals"})
async def list_proposals(
    project_id: int, ctx: Context, status: Literal["proposed", "approved", "rejected", "rolled_back"] | None = "proposed"
) -> list[dict[str, object]]:
    """List agent proposals waiting for (or decided by) the writer."""
    async with authorized(ctx, project_id, "screenplay.read", "list_proposals", {"status": status}) as session:
        rows = [row for row in await proposals_crud.list_for_project(session, project_id) if status is None or row.status == status]
        return _bounded([_dump(AgentProposalRead, row) for row in rows[-200:]])


@mcp.tool(annotations=WRITE, tags={"proposals"})
async def reject_proposal(project_id: int, proposal_id: int, ctx: Context, approval_id: int | None = None) -> dict[str, object]:
    """Reject a pending agent proposal on the writer's behalf (needs the writer's approval)."""
    arguments = {"project_id": project_id, "proposal_id": proposal_id}
    async with authorized(ctx, project_id, "screenplay.approve", "reject", {"proposal_id": proposal_id}, approval_id=approval_id, arguments=arguments) as session:
        return (await proposals.reject(session, project_id, proposal_id)).model_dump(mode="json")


@mcp.tool(annotations=WRITE, tags={"proposals"})
async def reject_timeline_proposal(project_id: int, screenplay_id: int, proposal_id: int, ctx: Context, approval_id: int | None = None) -> dict[str, object]:
    """Reject a pending scene-reorder proposal (needs the writer's approval)."""
    arguments = {"project_id": project_id, "screenplay_id": screenplay_id, "proposal_id": proposal_id}
    async with authorized(ctx, project_id, "timeline.approve", "reject", {"proposal_id": proposal_id}, approval_id=approval_id, arguments=arguments) as session:
        return (await timeline_proposals.reject(session, project_id, screenplay_id, proposal_id)).model_dump(mode="json")


# --- canon graph and artifacts ------------------------------------------------------------------


@mcp.tool(annotations=WRITE, tags={"canon"})
async def write_canon_node(
    project_id: int,
    ctx: Context,
    kind: str | None = None,
    label: str | None = None,
    description: str | None = None,
    node_id: int | None = None,
    expected_version: int | None = None,
    delete: bool = False,
    approval_id: int | None = None,
) -> dict[str, object]:
    """Create (no node_id), edit (node_id + expected_version) or delete (delete=true) a canon node: theme, motif, rule, prop, era..."""
    arguments = {"project_id": project_id, "kind": kind, "label": label, "description": description, "node_id": node_id, "expected_version": expected_version, "delete": delete}
    action = "delete" if delete else "update" if node_id else "create"
    async with authorized(ctx, project_id, "knowledge_graph.write", action, {"node_id": node_id}, approval_id=approval_id, arguments=arguments) as session:
        if node_id is None:
            if not kind or not label:
                raise ToolError("kind and label are required to create a node")
            node = await studio.create_node(session, project_id, kind, label, description)
        elif delete:
            await studio.delete_node(session, project_id, node_id, expected_version)
            return {"deleted_node_id": node_id}
        else:
            changes = {key: value for key, value in (("kind", kind), ("label", label), ("description", description)) if value is not None}
            node = await studio.update_node(session, project_id, node_id, changes, expected_version)
        return node.model_dump(mode="json")


@mcp.tool(annotations=WRITE, tags={"canon"})
async def write_canon_edge(
    project_id: int,
    ctx: Context,
    source_node_id: int | None = None,
    target_node_id: int | None = None,
    relation: str | None = None,
    edge_id: int | None = None,
    approval_id: int | None = None,
) -> dict[str, object]:
    """Relate two canon nodes, or delete a relationship by ``edge_id``."""
    arguments = {"project_id": project_id, "source_node_id": source_node_id, "target_node_id": target_node_id, "relation": relation, "edge_id": edge_id}
    async with authorized(ctx, project_id, "knowledge_graph.write", "delete_edge" if edge_id else "create_edge", {}, approval_id=approval_id, arguments=arguments) as session:
        if edge_id is not None:
            await studio.delete_edge(session, project_id, edge_id)
            return {"deleted_edge_id": edge_id}
        if source_node_id is None or target_node_id is None or not relation:
            raise ToolError("source_node_id, target_node_id and relation are required")
        return (await studio.create_edge(session, project_id, source_node_id, target_node_id, relation)).model_dump(mode="json")


@mcp.tool(annotations=WRITE, tags={"artifacts"})
async def write_artifact(
    project_id: int,
    ctx: Context,
    kind: str | None = None,
    title: str | None = None,
    content: str | None = None,
    artifact_id: int | None = None,
    expected_version: int | None = None,
    delete: bool = False,
    approval_id: int | None = None,
) -> dict[str, object]:
    """Create (no artifact_id), edit or delete a story artifact such as a series bible, research notes or a treatment."""
    arguments = {"project_id": project_id, "kind": kind, "title": title, "content": content, "artifact_id": artifact_id, "expected_version": expected_version, "delete": delete}
    action = "delete" if delete else "update" if artifact_id else "create"
    async with authorized(ctx, project_id, "artifacts.write", action, {"artifact_id": artifact_id}, approval_id=approval_id, arguments=arguments) as session:
        if artifact_id is None:
            if not kind or not title:
                raise ToolError("kind and title are required to create an artifact")
            artifact = await studio.create_artifact(session, project_id, kind, title, content or "")
        elif delete:
            await studio.delete_artifact(session, project_id, artifact_id, expected_version)
            return {"deleted_artifact_id": artifact_id}
        else:
            changes = {key: value for key, value in (("title", title), ("content", content)) if value is not None}
            artifact = await studio.update_artifact(session, project_id, artifact_id, changes, expected_version)
        return _dump(StoryArtifactRead, artifact)


# --- twins --------------------------------------------------------------------------------------


@mcp.tool(annotations=WRITE, tags={"twins"})
async def refresh_story_twin_now(project_id: int, ctx: Context) -> dict[str, int]:
    """Re-derive characters and locations from the working draft now (writer edits are kept)."""
    async with authorized(ctx, project_id, "twins.refresh", "refresh") as session:
        return await refresh_story_twin(session, project_id)


@mcp.tool(annotations=READ, tags={"twins"})
async def read_writer_twin(project_id: int, ctx: Context) -> dict[str, object]:
    """Read the writer's profile, memories and the brief agents receive about them."""
    async with authorized(ctx, project_id, "writer.read", "read") as session:
        profile = await get_writer_profile(session)
        from sqlmodel import select

        memories = [row for row in (await session.exec(select(WriterMemory))).all() if row.project_id in (None, project_id)]
        return {
            "profile": profile.model_dump(mode="json"),
            "memories": [memory.model_dump(mode="json") for memory in memories],
            "brief": await writer_twin_brief(session, project_id),
        }


@mcp.tool(annotations=WRITE, tags={"twins"})
async def remember_writer_preference(
    project_id: int, text: str, ctx: Context, kind: str = "preference", this_project_only: bool = False, approval_id: int | None = None
) -> dict[str, object]:
    """Remember something about how the writer works (needs the writer's approval)."""
    arguments = {"project_id": project_id, "text": text, "kind": kind, "this_project_only": this_project_only}
    async with authorized(ctx, project_id, "writer.write", "remember", {"kind": kind}, approval_id=approval_id, arguments=arguments) as session:
        memory = await studio.add_writer_memory(session, text, kind, project_id if this_project_only else None)
        return memory.model_dump(mode="json")


# --- resources and prompts ----------------------------------------------------------------------


@mcp.resource("draftpilot://projects/{project_id}/storyline")
async def storyline_resource(project_id: int, ctx: Context) -> str:
    """Publish the storyline."""
    async with authorized(ctx, project_id, "story.read", "read") as session:
        return json.dumps(storyline.storyline(await structure.require_project(session, project_id)), default=str)


@mcp.resource("draftpilot://projects/{project_id}/characters")
async def characters_resource(project_id: int, ctx: Context) -> str:
    """Publish the cast with profiles."""
    async with authorized(ctx, project_id, "story.read", "read") as session:
        return json.dumps(_bounded([_entity("character", row) for row in await entities.list_entities(session, project_id, "character")]))


@mcp.resource("draftpilot://projects/{project_id}/outline")
async def outline_resource(project_id: int, ctx: Context) -> str:
    """Publish the outline beats in order."""
    async with authorized(ctx, project_id, "story.read", "read") as session:
        return json.dumps(_bounded([_entity("beat", row) for row in await entities.list_entities(session, project_id, "beat")]))


@mcp.resource("draftpilot://projects/{project_id}/locations")
async def locations_resource(project_id: int, ctx: Context) -> str:
    """Publish the locations."""
    async with authorized(ctx, project_id, "story.read", "read") as session:
        return json.dumps(_bounded([_entity("location", row) for row in await entities.list_entities(session, project_id, "location")]))


@mcp.resource("draftpilot://projects/{project_id}/timeline")
async def timeline_resource(project_id: int, ctx: Context) -> str:
    """Publish every character timeline event."""
    async with authorized(ctx, project_id, "story.read", "read") as session:
        return json.dumps(_bounded([_entity("timeline_event", row) for row in await entities.list_entities(session, project_id, "timeline_event")]))


_GROUND_RULES = (
    "Work through DraftPilot's tools. Read before you write: start with read_story_context and read_storyline. "
    "Writes need the writer's approval: either call propose_* tools (the writer reviews proposals in DraftPilot), "
    "or call a write tool, and when it answers that approval request N is pending, ask the writer to approve it "
    "in DraftPilot and retry with approval_id=N. Always pass the expected_version you last read."
)


@mcp.prompt(tags={"workflow"})
def develop_storyline(project_id: int, idea: str = "") -> str:
    """Guide an agent from an idea to a logline, premise, synopsis, theme and tone."""
    return (
        f"Develop the storyline of DraftPilot project {project_id}. {_GROUND_RULES}\n"
        f"Idea from the writer: {idea or '(read the project brief)'}\n"
        "1. Read the storyline and story context. 2. Offer three logline options and ask the writer to choose. "
        "3. Propose premise, synopsis (one page), theme and tone with propose_story_change(kind='storyline', action='update')."
    )


@mcp.prompt(tags={"workflow"})
def develop_characters(project_id: int, focus: str = "") -> str:
    """Guide an agent through building the cast: profiles, motives, objectives, arcs, relationships, timelines."""
    return (
        f"Develop the characters of DraftPilot project {project_id}. {_GROUND_RULES}\n"
        f"Focus: {focus or 'the whole cast'}\n"
        "1. Read the storyline and list_story_entities(kind='character'). 2. For each lead, propose a profile with want, need, "
        "motive, objective, flaw and arc_summary. 3. Propose relationships between them. 4. For each lead, propose 4-8 timeline "
        "events (story_time, title, objective, emotional_state) that trace their arc across the story."
    )


@mcp.prompt(tags={"workflow"})
def build_outline(project_id: int, structure_hint: str = "three acts") -> str:
    """Guide an agent from storyline and cast to an act-by-act beat outline."""
    return (
        f"Build the outline of DraftPilot project {project_id} in {structure_hint}. {_GROUND_RULES}\n"
        "1. Read the storyline, the cast and read_outline. 2. Draft causally linked beats per act (setup, inciting incident, "
        "turns, midpoint, crisis, climax, resolution), each tied to the characters it moves. 3. Submit them with propose_outline."
    )


@mcp.prompt(tags={"workflow"})
def draft_script(project_id: int, beat_ids: str = "") -> str:
    """Guide an agent from outline beats to written screenplay scenes."""
    return (
        f"Write screenplay scenes for DraftPilot project {project_id}. {_GROUND_RULES}\n"
        f"Beats to dramatise: {beat_ids or 'the next unwritten beats in read_outline'}\n"
        "For each beat: write the scene in Fountain (heading, action, character cues, dialogue) true to each character's voice "
        "and objective, create it with create_scene(fountain=...), then link it to the beat with update_story_entity(kind='beat', "
        "fields={'scene_ids': [...], 'status': 'drafted'})."
    )


@mcp.prompt(tags={"workflow"})
def review_script(project_id: int, lens: str = "story, character and pacing") -> str:
    """Guide an agent through a coverage-style review that ends in reviewable proposals."""
    return (
        f"Review DraftPilot project {project_id} for {lens}. {_GROUND_RULES}\n"
        "Read the outline, the cast and scenes (read_screenplay_scenes). Report strengths, problems with scene citations, and "
        "propose concrete fixes with propose_screenplay_change or propose_story_change; or start the room's coverage or "
        "continuity workflow with start_room_workflow."
    )


# --- references, writer profile, search, evaluation ---------------------------------------------


@mcp.tool(annotations=WRITE, tags={"projects"})
async def write_reference(
    project_id: int,
    ctx: Context,
    label: str | None = None,
    kind: str = "other",
    url: str | None = None,
    note: str | None = None,
    reference_id: int | None = None,
    expected_version: int | None = None,
    delete: bool = False,
    approval_id: int | None = None,
) -> dict[str, object]:
    """Add (no reference_id), edit or delete a creative reference: a film, book, director, artwork or style."""
    from draftpilot.crud import project_references as references_crud
    from draftpilot.models import (
        ProjectReference,
        ProjectReferenceRead,
        ProjectReferenceUpdate,
    )

    arguments = {"project_id": project_id, "label": label, "kind": kind, "url": url, "note": note, "reference_id": reference_id, "expected_version": expected_version, "delete": delete}
    action = "delete" if delete else "update" if reference_id else "create"
    async with authorized(ctx, project_id, "projects.update", f"reference_{action}", {}, approval_id=approval_id, arguments=arguments) as session:
        await structure.require_project(session, project_id)
        if reference_id is None:
            if not label:
                raise ToolError("label is required to add a reference")
            try:
                reference_kind = ReferenceKind(kind)
            except ValueError as exc:
                raise ToolError(f"Unknown reference kind; expected one of {', '.join(item.value for item in ReferenceKind)}") from exc
            row = ProjectReference(project_id=project_id, kind=reference_kind, label=label[:300], url=url, note=note)
            session.add(row)
            await session.commit()
            await session.refresh(row)
        else:
            existing = await references_crud.get(session, reference_id)
            if existing is None or existing.project_id != project_id:
                raise ToolError("Reference not found")
            if expected_version != existing.version:
                raise ToolError("Reference has changed; read it again")
            if delete:
                await references_crud.delete(session, existing)
                return {"deleted_reference_id": reference_id}
            changes = {key: value for key, value in (("label", label), ("url", url), ("note", note)) if value is not None}
            row = await references_crud.update(session, existing, ProjectReferenceUpdate.model_validate(changes))
        return _dump(ProjectReferenceRead, row)


@mcp.tool(annotations=WRITE, tags={"twins"})
async def update_writer_profile(project_id: int, fields: dict[str, Any], ctx: Context, approval_id: int | None = None) -> dict[str, object]:
    """Update the writer profile: name, pen_name, bio, style_notes, default_format, default_language, preferences."""
    arguments = {"project_id": project_id, "fields": fields}
    async with authorized(ctx, project_id, "writer.write", "update_profile", {"fields": sorted(fields)}, approval_id=approval_id, arguments=arguments) as session:
        return (await studio.update_writer_profile(session, fields)).model_dump(mode="json")


@mcp.tool(annotations=WRITE, tags={"retrieval"})
async def reindex_project_search(project_id: int, ctx: Context) -> dict[str, object]:
    """Rebuild the project's search index (scenes, artifacts, story, canon) after a bulk change."""
    from draftpilot.core import temporal

    async with authorized(ctx, project_id, "context.read", "reindex") as session:
        await structure.require_project(session, project_id)
    return {"queued": await temporal.start_best_effort("reindex_project", project_id, description="Project reindex enqueue")}


@mcp.tool(annotations=WRITE, tags={"evaluations"})
async def start_evaluation(project_id: int, ctx: Context, screenplay_id: int | None = None, evaluator: str = "deterministic_review") -> dict[str, object]:
    """Start a screenplay evaluation run; follow it with read_workflow_run and read the result with read_project_evaluations."""
    from draftpilot.core import temporal
    from draftpilot.crud import workflow_runs as runs_crud
    from draftpilot.models import WorkflowRunCreate, WorkflowRunRead

    async with authorized(ctx, project_id, "evaluations.read", "start", {"evaluator": evaluator}) as session:
        draft = await structure.screenplay_in_project(session, project_id, screenplay_id)
        run = await runs_crud.create(
            session,
            WorkflowRunCreate(
                project_id=project_id,
                kind="evaluation",
                input={"screenplay_id": draft.id, "evaluator": evaluator},
                agent_role="audience_evaluator",
                max_attempts=3,
            ),
        )
    await temporal.start_run(run.id)
    return WorkflowRunRead.model_validate(run).model_dump(mode="json")
