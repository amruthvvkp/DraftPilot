"""Measure how useful the room is: acceptance, retention, writer feedback, cost and reliability.

* **Acceptance**: of the proposals the writer decided, the share approved (a later rollback counts
  as a rejection).
* **Retention**: of the blocks an approved proposal wrote, the share that still carry its authorship
  (``origin == "proposal:<id>"``). A writer edit takes authorship back, so retention falls as the
  writer rewrites the agent's words.
* **Feedback**: thumbs up and down on runs.
* **Usefulness**: the mean of whichever of acceptance, retention and the thumbs-up share are known.

Every score also goes to Langfuse, attached to the run's traces, when keys are configured.
"""

from collections import defaultdict
from statistics import mean
from typing import Any

import httpx
import logfire
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.config import settings
from draftpilot.core.queue import enqueue_best_effort
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


# ---------------------------------------------------------------------------------------------------------------------
# Langfuse scores
# ---------------------------------------------------------------------------------------------------------------------


def scores_enabled() -> bool:
    """Return whether Langfuse score keys are configured."""
    return bool(settings.otel.langfuse_public_key and settings.otel.langfuse_secret_key.get_secret_value())


async def traces_for_run(session: AsyncSession, workflow_run_id: int | None) -> list[str]:
    """Return the trace ids of every agent run a workflow run made."""
    if workflow_run_id is None:
        return []
    rows = await session.exec(select(AgentRun.trace_id).where(AgentRun.workflow_run_id == workflow_run_id))
    return sorted({trace for trace in rows.all() if trace})


async def score_traces(traces: list[str], name: str, value: float, comment: str = "") -> None:
    """Queue one score for each trace (best-effort; never fails the caller)."""
    if traces and scores_enabled():
        scores = [{"trace_id": trace, "name": name, "value": value, "comment": comment[:500]} for trace in traces]
        await enqueue_best_effort("push_langfuse_scores", scores, description="Langfuse score enqueue")


async def push_scores(scores: list[dict[str, Any]]) -> int:
    """POST scores to Langfuse's public API and return how many it accepted."""
    if not scores_enabled():
        return 0
    auth = (settings.otel.langfuse_public_key, settings.otel.langfuse_secret_key.get_secret_value())
    accepted = 0
    async with httpx.AsyncClient(base_url=settings.otel.langfuse_base_url, auth=auth, timeout=5.0) as client:
        for score in scores:
            payload = {"traceId": score["trace_id"], "name": score["name"], "value": score["value"], "dataType": "NUMERIC"}
            if score.get("comment"):
                payload["comment"] = score["comment"]
            try:
                response = await client.post("/api/public/scores", json=payload)
                response.raise_for_status()
                accepted += 1
            except httpx.HTTPError as exc:
                logfire.warning("Langfuse score skipped: {exc}", exc=str(exc))
    return accepted


DECISION_VALUES = {"approved": 1.0, "rejected": 0.0, "rolled_back": 0.0}


async def record_decision(session: AsyncSession, proposal: AgentProposal) -> None:
    """Score the traces behind a proposal with the writer's decision on it."""
    value = DECISION_VALUES.get(proposal.status)
    if value is not None:
        summary = str(proposal.diff.get("summary", "")) if isinstance(proposal.diff, dict) else ""
        await score_traces(await traces_for_run(session, proposal.run_id), f"proposal_{proposal.status}", value, summary)
