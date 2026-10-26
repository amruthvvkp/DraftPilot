"""Typed agent proposals: creation, approval, rejection and rollback, shared by REST, MCP and the room."""

from datetime import UTC, datetime
from typing import Any, cast

from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import events, indexing, temporal
from draftpilot.core.agent_roles import normalize_permission_mode
from draftpilot.core.errors import Conflict, Forbidden, Invalid, NotFound
from draftpilot.core.scene_proposals import (
    append_scenes,
    apply_scene_rewrite,
    remove_appended_scenes,
    rewrite_snapshot,
)
from draftpilot.core.scene_sync import SceneLike, scene_changed
from draftpilot.core.screenplay.schema import BlockDoc
from draftpilot.core.story.proposals import STORY_TARGETS, approve_story, rollback_story
from draftpilot.crud import acts as acts_crud
from draftpilot.crud import agent_proposals as proposals_crud
from draftpilot.crud import blocks as blocks_crud
from draftpilot.crud import dialogue_translations as translations_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.crud import workflow_runs as runs_crud
from draftpilot.models import (
    AgentProposal,
    AgentProposalRead,
    BlockType,
    DialogueTranslation,
    Scene,
)


class ProposalCreateRequest(BaseModel):
    """Describe a typed, reviewable operation proposed by an agent."""

    target_kind: str = Field(pattern="^(scene|block|artifact|dialogue_translation)$")
    target_id: int
    scene_id: int | None = None
    operation: dict[str, Any] = Field(min_length=1)
    diff: dict[str, Any] = Field(default_factory=dict)
    base_version: int = Field(ge=1)
    run_id: int | None = None


async def _authorize_proposal_mode(
    session: AsyncSession,
    project_id: int,
    run_id: int | None,
    target_kind: str,
    target_id: int,
    scene_id: int | None,
) -> None:
    """Authorize proposal creation against the originating run's server scope."""
    if run_id is None:
        return
    run = await runs_crud.get(session, run_id)
    if run is None or run.project_id != project_id:
        raise NotFound("Proposal run not found")
    permission_mode = normalize_permission_mode(run.permission_mode)
    if permission_mode == "chat_only":
        raise Forbidden("Chat-only agent runs cannot create change proposals")
    if permission_mode == "scoped_edit":
        scope = run.input.get("scope")
        if not isinstance(scope, dict):
            raise Forbidden("Scoped edit run has no server-defined target scope")
        if scope.get("target_kind") != target_kind or scope.get("target_id") != target_id:
            raise Forbidden("Proposal target is outside the agent run scope")
        scoped_scene_id = scope.get("scene_id")
        if scoped_scene_id is not None and scoped_scene_id != scene_id:
            raise Forbidden("Proposal scene is outside the agent run scope")


def _validate_operation(target_kind: str, operation: dict[str, Any]) -> None:
    """Reject operation fields that do not belong to the selected target type."""
    allowed = {
        "scene": {"heading", "body", "blocks"},
        "block": {"element_type", "text", "is_dual", "dual_group"},
        "artifact": {"title", "content", "depends_on", "artifact_metadata"},
        "dialogue_translation": {"language", "text", "status"},
    }[target_kind]
    if not operation or set(operation) - allowed:
        raise Invalid("Unsupported typed operation")
    if target_kind == "block":
        if "element_type" in operation and operation["element_type"] not in {item.value for item in BlockType}:
            raise Invalid("Invalid screenplay block type")
        if "text" in operation and not isinstance(operation["text"], str):
            raise Invalid("Invalid screenplay block text")
        if "is_dual" in operation and not isinstance(operation["is_dual"], bool):
            raise Invalid("Invalid dual-dialogue marker")
        if "dual_group" in operation and operation["dual_group"] is not None and not isinstance(operation["dual_group"], int):
            raise Invalid("Invalid dual-dialogue group")
    if target_kind == "scene" and "blocks" in operation:
        blocks = operation["blocks"]
        if "body" in operation or not isinstance(blocks, list) or not blocks or len(blocks) > 400:
            raise Invalid("Invalid scene rewrite")
        try:
            [BlockDoc.model_validate(item) for item in blocks]
        except ValueError as exc:
            raise Invalid("Invalid scene rewrite") from exc
    if target_kind == "dialogue_translation" and (
        not isinstance(operation.get("language"), str)
        or not isinstance(operation.get("text"), str)
    ):
        raise Invalid("Invalid translation operation")


async def _scene_in_project(
    session: AsyncSession, project_id: int, scene_id: int
) -> Any | None:
    """Return a scene in the requested project or ``None``."""
    scene = await scenes_crud.get(session, scene_id)
    act = await acts_crud.get(session, scene.act_id) if scene else None
    screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
    if scene is None or screenplay is None or screenplay.project_id != project_id:
        return None
    return scene


async def _dialogue_target(
    session: AsyncSession, project_id: int, scene_id: int, block_id: int
) -> tuple[Any, Any] | None:
    """Return a dialogue block and scene in the requested project."""
    scene = await _scene_in_project(session, project_id, scene_id)
    block = await blocks_crud.get(session, block_id)
    if scene is None or block is None or block.scene_id != scene_id or block.element_type.value != "dialogue":
        return None
    return scene, block


async def _block_target(
    session: AsyncSession, project_id: int, scene_id: int, block_id: int
) -> tuple[Any, Any] | None:
    """Return any screenplay block and its project-scoped scene."""
    scene = await _scene_in_project(session, project_id, scene_id)
    block = await blocks_crud.get(session, block_id)
    if scene is None or block is None or block.scene_id != scene_id:
        return None
    return scene, block


async def _approve_appended_scenes(
    session: AsyncSession, project_id: int, proposal: AgentProposal
) -> AgentProposalRead:
    """Append a proposal's new scenes to its screenplay and remember their ids for rollback."""
    screenplay = await screenplays_crud.get(session, proposal.target_id)
    scenes = proposal.operation.get("append_scenes")
    if screenplay is None or screenplay.project_id != project_id:
        raise NotFound("Proposal target not found")
    if not isinstance(scenes, list) or not scenes:
        raise Invalid("Invalid scene append")
    created = await append_scenes(session, proposal.target_id, scenes, f"proposal:{proposal.id}")
    proposal.status = "approved"
    proposal.diff = {**proposal.diff, "created_scene_ids": created}
    proposal.updated_at = datetime.now(UTC)
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    for scene_id in created:
        scene = await scenes_crud.get(session, scene_id)
        if scene is not None:
            await scene_changed(session, project_id, cast(SceneLike, scene), reason="proposal.approved")
    await events.publish(project_id, "proposal.changed", {"proposal_id": proposal.id, "status": "approved"})
    return AgentProposalRead.model_validate(proposal)


async def _rollback_appended_scenes(
    session: AsyncSession, project_id: int, proposal: AgentProposal
) -> AgentProposalRead:
    """Remove the scenes an approved append created, unless the writer has since edited them."""
    created = proposal.diff.get("created_scene_ids")
    if not isinstance(created, list):
        raise Invalid("Invalid scene append rollback")
    try:
        await remove_appended_scenes(session, [int(item) for item in created])
    except ValueError as exc:
        raise Conflict(str(exc)) from exc
    proposal.status = "rolled_back"
    proposal.updated_at = datetime.now(UTC)
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    await events.publish(project_id, "screenplay.changed", {"screenplay_id": proposal.target_id, "reason": "proposal.rolled_back"})
    return AgentProposalRead.model_validate(proposal)


async def create_proposal(session: AsyncSession, project_id: int, data: ProposalCreateRequest) -> AgentProposalRead:
    """Persist a proposal after deriving its target version server-side."""
    await _authorize_proposal_mode(
        session, project_id, data.run_id, data.target_kind, data.target_id, data.scene_id
    )
    _validate_operation(data.target_kind, data.operation)
    target: Any | None
    if data.target_kind == "scene":
        target = await _scene_in_project(session, project_id, data.target_id)
    elif data.target_kind == "block":
        if data.scene_id is None:
            raise Invalid("scene_id is required")
        block_target = await _block_target(session, project_id, data.scene_id, data.target_id)
        target = block_target[0] if block_target else None
    elif data.target_kind == "dialogue_translation":
        if data.scene_id is None:
            raise Invalid("scene_id is required")
        dialogue_target = await _dialogue_target(session, project_id, data.scene_id, data.target_id)
        target = dialogue_target[0] if dialogue_target else None
    else:
        target = await artifacts_crud.get(session, data.target_id)
        if target is not None and target.project_id != project_id:
            target = None
    if target is None:
        raise NotFound("Proposal target not found")
    version = getattr(target, "version", None)
    if version != data.base_version:
        raise Conflict("Proposal target has changed")
    if data.target_kind == "dialogue_translation":
        assert data.scene_id is not None
        existing = next(
            (item for item in await translations_crud.list_for_block(session, data.target_id)
             if item.language == data.operation.get("language")),
            None,
        )
        snapshot = {
            "exists": existing is not None,
            "scene_id": data.scene_id,
            "language": existing.language if existing else data.operation.get("language"),
            "text": existing.text if existing else "",
            "status": existing.status if existing else "draft",
        }
    elif data.target_kind == "block":
        assert data.scene_id is not None
        snapshot = {"scene_id": data.scene_id}
        block_target = await _block_target(session, project_id, data.scene_id, data.target_id)
        if block_target is None:
            raise NotFound("Proposal target not found")
        snapshot.update(
            {
                key: (
                    getattr(block_target[1], key).value
                    if key == "element_type"
                    else getattr(block_target[1], key)
                )
                for key in data.operation
            }
        )
        # Rollback restores every "before" key, so the block's prior authorship comes back too.
        snapshot["origin"] = block_target[1].origin
    elif data.target_kind == "scene" and "blocks" in data.operation:
        snapshot = await rewrite_snapshot(session, cast(Scene, target))
    else:
        before = data.operation.keys() & {"title", "content", "depends_on", "artifact_metadata", "heading", "body"}
        snapshot = {key: getattr(target, key) for key in before}
    proposal = await proposals_crud.create(
        session,
        AgentProposal(
            project_id=project_id,
            run_id=data.run_id,
            target_kind=data.target_kind,
            target_id=data.target_id,
            operation=data.operation,
            diff=data.diff,
            before=snapshot,
            base_version=data.base_version,
        ),
    )
    return AgentProposalRead.model_validate(proposal)


async def _approve(session: AsyncSession, project_id: int, proposal_id: int) -> AgentProposalRead:
    """Apply a typed proposal only when its target version is unchanged."""
    proposal = await proposals_crud.get(session, proposal_id)
    if proposal is None or proposal.project_id != project_id:
        raise NotFound("Proposal not found")
    if proposal.status != "proposed":
        raise Conflict("Proposal is not pending")
    if proposal.target_kind == "screenplay":
        return await _approve_appended_scenes(session, project_id, proposal)
    if proposal.target_kind in STORY_TARGETS:
        return await approve_story(session, project_id, proposal)
    await _authorize_proposal_mode(
        session,
        project_id,
        proposal.run_id,
        proposal.target_kind,
        proposal.target_id,
        proposal.before.get("scene_id") if isinstance(proposal.before.get("scene_id"), int) else None,
    )
    target: Any | None
    block_target: tuple[Any, Any] | None = None
    if proposal.target_kind == "scene":
        target = await _scene_in_project(session, project_id, proposal.target_id)
    elif proposal.target_kind == "block":
        scene_id = proposal.before.get("scene_id")
        if isinstance(scene_id, int):
            block_target = await _block_target(session, project_id, scene_id, proposal.target_id)
        target = block_target[0] if block_target else None
    elif proposal.target_kind == "dialogue_translation":
        scene_id = proposal.before.get("scene_id")
        target = None
        if isinstance(scene_id, int):
            dialogue_target = await _dialogue_target(session, project_id, scene_id, proposal.target_id)
            target = dialogue_target[0] if dialogue_target else None
    else:
        target = await artifacts_crud.get(session, proposal.target_id)
        if target is not None and target.project_id != project_id:
            target = None
    if target is None or getattr(target, "version", None) != proposal.base_version:
        raise Conflict("Proposal target has changed")
    if proposal.target_kind == "block":
        assert block_target is not None
    elif proposal.target_kind == "dialogue_translation":
        language = proposal.operation.get("language")
        text = proposal.operation.get("text")
        if not isinstance(language, str) or not isinstance(text, str):
            raise Invalid("Invalid translation operation")
        existing = next(
            (item for item in await translations_crud.list_for_block(session, proposal.target_id)
             if item.language == language),
            None,
        )
        if existing is None:
            session.add(DialogueTranslation(block_id=proposal.target_id, language=language, text=text, source_version=target.version))
        else:
            existing.text = text
            existing.status = str(proposal.operation.get("status", "draft"))
            existing.source_version = target.version
            session.add(existing)
        proposal.status = "approved"
        proposal.updated_at = datetime.now(UTC)
        session.add(proposal)
        await session.commit()
        await session.refresh(proposal)
        await indexing.index_document(
            project_id,
            f"translation:{proposal.target_id}",
            "dialogue_translation",
            text,
            target.version,
        )
        await events.publish(project_id, "translation.changed", {"block_id": proposal.target_id, "language": language})
        return AgentProposalRead.model_validate(proposal)
    if proposal.target_kind == "block":
        if block_target is None:
            raise NotFound("Proposal target not found")
        _validate_operation("block", proposal.operation)
        block = block_target[1]
        for key, value in proposal.operation.items():
            setattr(block, key, BlockType(value) if key == "element_type" else value)
        block.origin = f"proposal:{proposal.id}"
        target.version += 1
        session.add(block)
        session.add(target)
        proposal.status = "approved"
        proposal.updated_at = datetime.now(UTC)
        session.add(proposal)
        await session.commit()
        await session.refresh(proposal)
        await scene_changed(session, project_id, cast(SceneLike, target), reason="proposal.approved")
        return AgentProposalRead.model_validate(proposal)
    operation = proposal.operation
    if proposal.target_kind == "scene" and "blocks" in operation:
        _validate_operation("scene", operation)
        heading = operation.get("heading")
        proposal.status = "approved"
        proposal.updated_at = datetime.now(UTC)
        session.add(proposal)
        await apply_scene_rewrite(
            session, cast(Scene, target), heading if isinstance(heading, str) else None, operation["blocks"], f"proposal:{proposal.id}"
        )
        await session.refresh(proposal)
        await scene_changed(session, project_id, cast(SceneLike, target), reason="proposal.approved")
        await events.publish(project_id, "proposal.changed", {"proposal_id": proposal.id, "status": "approved"})
        return AgentProposalRead.model_validate(proposal)
    allowed = (
        {"heading", "body", "blocks"}
        if proposal.target_kind == "scene"
        else {"title", "content", "depends_on", "artifact_metadata"}
    )
    if set(operation) - allowed:
        raise Invalid("Unsupported typed operation")
    for key, value in operation.items():
        setattr(target, key, value)
    target.version += 1
    session.add(target)
    if proposal.target_kind == "artifact":
        await artifacts_crud.mark_dependents_stale(session, project_id, [proposal.target_id])
    proposal.status = "approved"
    proposal.updated_at = datetime.now(UTC)
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    if proposal.target_kind == "scene":
        await scene_changed(session, project_id, cast(SceneLike, target), reason="proposal.approved")
    else:
        await events.publish(project_id, "artifact.changed", {"artifact_id": target.id, "version": target.version})
    return AgentProposalRead.model_validate(proposal)


async def _reject(session: AsyncSession, project_id: int, proposal_id: int) -> AgentProposalRead:
    """Reject a pending proposal without touching its target."""
    proposal = await proposals_crud.get(session, proposal_id)
    if proposal is None or proposal.project_id != project_id:
        raise NotFound("Proposal not found")
    if proposal.status != "proposed":
        raise Conflict("Proposal is not pending")
    proposal.status = "rejected"
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    await events.publish(project_id, "proposal.changed", {"proposal_id": proposal.id, "status": "rejected"})
    return AgentProposalRead.model_validate(proposal)


async def rollback(session: AsyncSession, project_id: int, proposal_id: int) -> AgentProposalRead:
    """Rollback an approved proposal as a new versioned target mutation."""
    proposal = await proposals_crud.get(session, proposal_id)
    if proposal is None or proposal.project_id != project_id:
        raise NotFound("Proposal not found")
    if proposal.status != "approved":
        raise Conflict("Proposal is not approved")
    if proposal.target_kind == "screenplay":
        return await _rollback_appended_scenes(session, project_id, proposal)
    if proposal.target_kind in STORY_TARGETS:
        return await rollback_story(session, project_id, proposal)
    target: Any | None
    block_target: tuple[Any, Any] | None = None
    if proposal.target_kind == "scene":
        target = await _scene_in_project(session, project_id, proposal.target_id)
    elif proposal.target_kind == "block":
        scene_id = proposal.before.get("scene_id")
        if isinstance(scene_id, int):
            block_target = await _block_target(session, project_id, scene_id, proposal.target_id)
        target = block_target[0] if block_target else None
    elif proposal.target_kind == "dialogue_translation":
        scene_id = proposal.before.get("scene_id")
        target = None
        if isinstance(scene_id, int):
            dialogue_target = await _dialogue_target(session, project_id, scene_id, proposal.target_id)
            target = dialogue_target[0] if dialogue_target else None
    else:
        target = await artifacts_crud.get(session, proposal.target_id)
        if target is not None and target.project_id != project_id:
            target = None
    if target is None:
        raise NotFound("Proposal target not found")
    if proposal.target_kind == "block":
        assert block_target is not None
    elif proposal.target_kind == "dialogue_translation":
        language = proposal.before.get("language")
        if not isinstance(language, str):
            raise Invalid("Invalid translation rollback")
        existing = next(
            (item for item in await translations_crud.list_for_block(session, proposal.target_id)
             if item.language == language),
            None,
        )
        if proposal.before.get("exists") and existing is not None:
            existing.text = str(proposal.before.get("text", ""))
            existing.status = str(proposal.before.get("status", "draft"))
            existing.source_version = target.version
            session.add(existing)
        elif existing is not None:
            await session.delete(existing)
    if proposal.target_kind == "scene" and "blocks" in proposal.before:
        proposal.status = "rolled_back"
        proposal.updated_at = datetime.now(UTC)
        session.add(proposal)
        await apply_scene_rewrite(session, cast(Scene, target), proposal.before.get("heading"), proposal.before["blocks"], None)
        await session.refresh(proposal)
        await scene_changed(session, project_id, cast(SceneLike, target), reason="proposal.rolled_back")
        return AgentProposalRead.model_validate(proposal)
    if proposal.target_kind == "block":
        if block_target is None:
            raise NotFound("Proposal target not found")
        block = block_target[1]
        for key, value in proposal.before.items():
            if key != "scene_id":
                setattr(block, key, BlockType(value) if key == "element_type" else value)
        session.add(block)
    for key, value in proposal.before.items():
        if key not in {"exists", "language", "text", "status", "scene_id"}:
            setattr(target, key, value)
    target.version += 1
    session.add(target)
    proposal.status = "rolled_back"
    proposal.updated_at = datetime.now(UTC)
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    if proposal.target_kind in {"block", "scene"}:
        await scene_changed(session, project_id, cast(SceneLike, target), reason="proposal.rolled_back")
    elif proposal.target_kind == "artifact":
        await events.publish(project_id, "artifact.changed", {"artifact_id": target.id, "version": target.version})
    return AgentProposalRead.model_validate(proposal)




async def _decided(proposal: AgentProposalRead) -> AgentProposalRead:
    """Tell the run that made a proposal (a waiting room workflow) that the writer decided it."""
    await temporal.signal_run(proposal.run_id, "proposal_decided", proposal.id, proposal.status)
    return proposal


async def approve(session: AsyncSession, project_id: int, proposal_id: int) -> AgentProposalRead:
    """Apply a typed proposal only when its target version is unchanged, and tell its run."""
    return await _decided(await _approve(session, project_id, proposal_id))


async def reject(session: AsyncSession, project_id: int, proposal_id: int) -> AgentProposalRead:
    """Reject a pending proposal without touching its target, and tell its run."""
    return await _decided(await _reject(session, project_id, proposal_id))
