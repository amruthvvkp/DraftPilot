"""Measure how useful the room is: acceptance, retention, writer feedback, cost and reliability.

* **Acceptance**: of the proposals the writer decided, the share approved (a later rollback counts
  as a rejection).
* **Retention**: of the blocks an approved proposal wrote, the share that still carry its authorship
  (``origin == "proposal:<id>"``). A writer edit takes authorship back, so retention falls as the
  writer rewrites the agent's words.
* **Feedback**: thumbs up and down on runs.
* **Usefulness**: the mean of whichever of acceptance, retention and the thumbs-up share are known.

Every measure lives in Postgres; nothing is pushed to an external trace store.
"""

from collections import defaultdict
from statistics import mean
from typing import Any

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import AgentFeedback, AgentProposal, AgentRun, Block, WorkflowRun

CHAT = "chat & MCP"


def written_blocks(proposal: AgentProposal) -> int:
    """Return how many blocks an approved proposal wrote."""
    if proposal.target_kind == "block":
        return 1
    if proposal.target_kind == "scene" and isinstance(proposal.operation.get("blocks"), list):
        return len(proposal.operation["blocks"])
    if proposal.target_kind == "screenplay":
        return sum(len(scene.get("blocks") or []) for scene in proposal.operation.get("append_scenes") or [])
    return 0


def _rate(numerator: int, denominator: int) -> float | None:
    """Return a ratio rounded for display, or ``None`` when nothing was measured."""
    return round(numerator / denominator, 3) if denominator else None


async def project_insights(session: AsyncSession, project_id: int) -> dict[str, Any]:
    """Return usefulness per room workflow and per role, plus project totals."""
    runs = {run.id: run for run in (await session.exec(select(WorkflowRun).where(WorkflowRun.project_id == project_id))).all()}
    workflow_of = {run_id: str(run.input.get("workflow") or run.kind) for run_id, run in runs.items() if run.kind == "room_workflow"}
    proposals = list((await session.exec(select(AgentProposal).where(AgentProposal.project_id == project_id))).all())
    retained = dict(
        (
            await session.exec(
                select(Block.origin, func.count())
                .where(col(Block.origin).in_([f"proposal:{proposal.id}" for proposal in proposals if proposal.status == "approved"]))
                .group_by(col(Block.origin))
            )
        ).all()
    )
    feedback = list((await session.exec(select(AgentFeedback).where(AgentFeedback.project_id == project_id))).all())
    agent_runs = list((await session.exec(select(AgentRun).where(AgentRun.project_id == project_id))).all())

    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"runs": 0, "succeeded": 0, "failed": 0, "cancelled": 0, "approved": 0, "rejected": 0, "rolled_back": 0,
                 "pending": 0, "written": 0, "kept": 0, "up": 0, "down": 0, "durations": []}
    )
    for run_id, key in workflow_of.items():
        run = runs[run_id]
        group = groups[key]
        group["runs"] += 1
        if run.status in {"succeeded", "failed", "cancelled"}:
            group[run.status] += 1
        if run.status == "succeeded":
            group["durations"].append((run.updated_at - run.created_at).total_seconds())
    for proposal in proposals:
        group = groups[workflow_of.get(proposal.run_id or 0, CHAT)]
        status = {"proposed": "pending"}.get(proposal.status, proposal.status)
        if status in group:
            group[status] += 1
        if proposal.status == "approved":
            group["written"] += written_blocks(proposal)
            group["kept"] += retained.get(f"proposal:{proposal.id}", 0)
    for item in feedback:
        group = groups[workflow_of.get(item.workflow_run_id or 0, CHAT)]
        group["up" if item.rating > 0 else "down"] += 1

    def summary(group: dict[str, Any]) -> dict[str, Any]:
        """Turn raw counts into rates and a usefulness score."""
        decided = group["approved"] + group["rejected"] + group["rolled_back"]
        acceptance = _rate(group["approved"], decided)
        retention = _rate(group["kept"], group["written"])
        thumbs = _rate(group["up"], group["up"] + group["down"])
        known = [value for value in (acceptance, retention, thumbs) if value is not None]
        durations = group.pop("durations")
        return {
            **group,
            "acceptance": acceptance,
            "retention": retention,
            "thumbs_up_share": thumbs,
            "usefulness": round(mean(known), 3) if known else None,
            "mean_duration_s": round(mean(durations), 1) if durations else None,
        }

    roles: dict[str, dict[str, Any]] = defaultdict(lambda: {"runs": 0, "failed": 0, "tokens": 0, "duration_ms": []})
    for agent_run in agent_runs:
        role = roles[agent_run.role]
        role["runs"] += 1
        role["failed"] += agent_run.status == "failed"
        role["tokens"] += agent_run.input_tokens + agent_run.output_tokens
        role["duration_ms"].append(agent_run.duration_ms)
    return {
        "workflows": {key: summary(group) for key, group in sorted(groups.items())},
        "roles": {
            key: {
                "runs": role["runs"],
                "failure_rate": _rate(role["failed"], role["runs"]),
                "tokens": role["tokens"],
                "mean_duration_s": round(mean(role["duration_ms"]) / 1000, 1) if role["duration_ms"] else None,
            }
            for key, role in sorted(roles.items())
        },
    }
