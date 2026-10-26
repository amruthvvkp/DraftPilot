"""Reviewable agent changes to the typed story: create, update or delete an entity, or edit the storyline.

An agent never writes these directly. It proposes; the writer approves (the change is applied
as the writer), rejects, or later rolls back an approved change.
"""

from datetime import UTC, datetime
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import events
from draftpilot.core.errors import Conflict, Invalid, NotFound
from draftpilot.core.story import entities
from draftpilot.core.story.storyline import STORYLINE_FIELDS, update_project
from draftpilot.core.story.structure import require_project
from draftpilot.crud import agent_proposals as proposals_crud
from draftpilot.models import AgentProposal, AgentProposalRead

STORY_TARGETS = frozenset({*entities.KINDS, "storyline", "outline"})
ACTIONS = ("create", "update", "delete")


async def propose_story_change(
    session: AsyncSession,
    project_id: int,
    kind: str,
    action: str,
    fields: dict[str, Any] | None = None,
    *,
    entity_id: int | None = None,
    run_id: int | None = None,
    summary: str = "",
) -> AgentProposal:
    """Validate and store a story change for the writer to decide."""
    await require_project(session, project_id)
    fields = dict(fields or {})
    if kind == "storyline":
        if action != "update" or not fields or set(fields) - set(STORYLINE_FIELDS):
            raise Invalid(f"A storyline proposal updates some of: {', '.join(STORYLINE_FIELDS)}")
        project = await require_project(session, project_id)
        before = {name: getattr(project, name) for name in fields}
        target_id, base_version = project_id, project.version
    else:
        spec = entities.entity_kind(kind)
        if action not in ACTIONS:
            raise Invalid(f"Unknown action {action!r}; expected one of {', '.join(ACTIONS)}")
        if action == "create":
            entities.validate_input(spec.create, fields)
            before, target_id, base_version = {}, 0, 1
        else:
            if entity_id is None:
                raise Invalid(f"{action} needs the {spec.label.lower()} id")
            row = await entities.get_entity(session, project_id, kind, entity_id)
            if action == "update":
                if not fields:
                    raise Invalid("An update proposal needs at least one field")
                entities.validate_input(spec.update, fields)
                current = entities.to_read(spec, row)
                before = {name: current.get(name) for name in fields}
            else:
                before = entities.to_read(spec, row)
            target_id, base_version = entity_id, row.version
    proposal = await proposals_crud.create(
        session,
        AgentProposal(
            project_id=project_id,
            run_id=run_id,
            target_kind=kind,
            target_id=target_id,
            operation={"action": action, "fields": fields},
            diff={"summary": summary or f"{action} {kind}"},
            before=before,
            base_version=base_version,
        ),
    )
    await events.publish(project_id, "proposal.changed", {"proposal_id": proposal.id, "status": "proposed"})
    return proposal


def _beat_signature(rows: list[Any]) -> list[list[int]]:
    """Identify a beat list by ids and versions, to detect edits since a proposal was made."""
    return [[row.id or 0, row.version] for row in rows]


async def propose_outline(
    session: AsyncSession,
    project_id: int,
    beats: list[dict[str, Any]],
    *,
    run_id: int | None = None,
    summary: str = "",
) -> AgentProposal:
    """Propose replacing the outline's beats; each beat has ``act`` (1-based), ``title``, ``summary``."""
    await require_project(session, project_id)
    if not beats:
        raise Invalid("An outline proposal needs at least one beat")
    cleaned = []
    for beat in beats:
        entities.validate_input(entities.entity_kind("beat").create, {"title": beat.get("title"), "summary": beat.get("summary", "")})
        cleaned.append(
            {
                "act": max(1, int(beat.get("act") or 1)),
                "title": str(beat["title"])[:300],
                "summary": str(beat.get("summary", ""))[:4000],
                "beat_type": str(beat.get("beat_type") or "beat")[:60],
            }
        )
    current = await entities.list_entities(session, project_id, "beat")
    proposal = await proposals_crud.create(
        session,
        AgentProposal(
            project_id=project_id,
            run_id=run_id,
            target_kind="outline",
            target_id=project_id,
            operation={"action": "set_beats", "beats": cleaned},
            diff={"summary": summary or f"{len(cleaned)}-beat outline", "base_beats": _beat_signature(current)},
            before={"beats": [entities.to_read(entities.entity_kind("beat"), row) for row in current]},
            base_version=1,
        ),
    )
    await events.publish(project_id, "proposal.changed", {"proposal_id": proposal.id, "status": "proposed"})
    return proposal


async def _acts_for_outline(session: AsyncSession, project_id: int, count: int) -> list[int]:
    """Return act ids of the working draft, creating acts so there are at least ``count``."""
    from draftpilot.core.story.structure import acts_for_project, create_act
    from draftpilot.core.twins import working_screenplay

    draft = await working_screenplay(session, project_id)
    if draft is None:
        return []
    acts = await acts_for_project(session, project_id, draft.id)
    titles = ("Act One", "Act Two", "Act Three", "Act Four", "Act Five")
    while len(acts) < count:
        acts.append(await create_act(session, project_id, draft.id, titles[len(acts)] if len(acts) < 5 else ""))
    return [act.id or 0 for act in acts]


async def _replace_beats(session: AsyncSession, project_id: int, beats: list[dict[str, Any]], source: str) -> list[int]:
    """Delete the current beats and create ``beats`` in order; return the new ids."""
    for row in await entities.list_entities(session, project_id, "beat"):
        await entities.delete_entity(session, project_id, "beat", row.id or 0, expected_version=None, require_version=False)
    act_ids = await _acts_for_outline(session, project_id, max((int(beat.get("act") or 1) for beat in beats), default=1))
    created = []
    for position, beat in enumerate(beats):
        values: dict[str, Any] = {key: beat[key] for key in ("title", "summary", "beat_type", "status", "scene_ids", "character_ids") if key in beat}
        act_index = int(beat.get("act") or 1) - 1
        if "act_id" in beat:
            values["act_id"] = beat["act_id"]
        elif act_ids:
            values["act_id"] = act_ids[min(act_index, len(act_ids) - 1)]
        row = await entities.create_entity(session, project_id, "beat", {**values, "position": position}, source=source)
        created.append(row.id or 0)
    return created


async def _finish(session: AsyncSession, project_id: int, proposal: AgentProposal, status: str, **diff: Any) -> AgentProposalRead:
    """Persist the proposal's new status and announce it."""
    proposal.status = status
    proposal.diff = {**proposal.diff, **diff}
    proposal.updated_at = datetime.now(UTC)
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    await events.publish(project_id, "proposal.changed", {"proposal_id": proposal.id, "status": status})
    return AgentProposalRead.model_validate(proposal)


async def approve_story(session: AsyncSession, project_id: int, proposal: AgentProposal) -> AgentProposalRead:
    """Apply an approved story proposal as the writer."""
    action, fields = proposal.operation.get("action"), dict(proposal.operation.get("fields") or {})
    kind = proposal.target_kind
    if kind == "storyline":
        project = await update_project(session, project_id, fields, proposal.base_version)
        return await _finish(session, project_id, proposal, "approved", applied_version=project.version)
    if kind == "outline":
        current = await entities.list_entities(session, project_id, "beat")
        if _beat_signature(current) != proposal.diff.get("base_beats"):
            raise Conflict("The outline has changed since this was proposed")
        created = await _replace_beats(session, project_id, list(proposal.operation.get("beats") or []), "agent")
        return await _finish(session, project_id, proposal, "approved", created_ids=created)
    if action == "create":
        row = await entities.create_entity(session, project_id, kind, fields, source="agent")
        return await _finish(session, project_id, proposal, "approved", created_id=row.id, applied_version=row.version)
    if action == "update":
        row = await entities.update_entity(
            session, project_id, kind, proposal.target_id, fields, expected_version=proposal.base_version
        )
        return await _finish(session, project_id, proposal, "approved", applied_version=row.version)
    if action == "delete":
        await entities.delete_entity(session, project_id, kind, proposal.target_id, expected_version=proposal.base_version)
        return await _finish(session, project_id, proposal, "approved")
    raise Invalid("Unsupported story proposal")


async def rollback_story(session: AsyncSession, project_id: int, proposal: AgentProposal) -> AgentProposalRead:
    """Undo an approved story proposal, refusing when the writer has changed the result since."""
    action, kind = proposal.operation.get("action"), proposal.target_kind
    applied = proposal.diff.get("applied_version")
    try:
        if kind == "storyline":
            await update_project(session, project_id, proposal.before, applied)
        elif kind == "outline":
            current = await entities.list_entities(session, project_id, "beat")
            if [row.id for row in current] != proposal.diff.get("created_ids") or any(row.version != 1 for row in current):
                raise Conflict("The writer has changed this since it was approved")
            await _replace_beats(session, project_id, list(proposal.before.get("beats") or []), "writer")
        elif action == "create":
            created = proposal.diff.get("created_id")
            if not isinstance(created, int):
                raise Invalid("Proposal has no created entity to remove")
            await entities.delete_entity(session, project_id, kind, created, expected_version=applied)
        elif action == "update":
            await entities.update_entity(
                session, project_id, kind, proposal.target_id, proposal.before, expected_version=applied
            )
        elif action == "delete":
            spec = entities.entity_kind(kind)
            restored = {name: proposal.before[name] for name in spec.create.model_fields if name in proposal.before}
            row = await entities.create_entity(session, project_id, kind, restored, source=str(proposal.before.get("source", "writer")))
            return await _finish(session, project_id, proposal, "rolled_back", restored_id=row.id)
    except Conflict:
        raise Conflict("The writer has changed this since it was approved") from None
    except NotFound:
        raise Conflict("The approved change no longer exists") from None
    return await _finish(session, project_id, proposal, "rolled_back")
