"""Test usefulness measurement: acceptance, retention, feedback, Langfuse scores, and online checks."""

import json
from collections.abc import AsyncGenerator, Iterator
from typing import Any

import httpx
import pytest
from _async import run_async
from _db import memory_session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.api.insights import router
from draftpilot.core import usefulness
from draftpilot.core.db import async_get_db
from draftpilot.evals.online import online_checks
from draftpilot.models import (
    Act,
    AgentProposal,
    AgentRun,
    Block,
    Project,
    Scene,
    Screenplay,
    WorkflowRun,
)


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, AsyncSession, list[Any]]]:
    """Seed one rewrite run with decided proposals, blocks, agent runs, and a feedback-ready API."""
    queued: list[Any] = []

    async def enqueue(function: str, *args: Any, **_kwargs: Any) -> None:
        """Capture queued score batches."""
        queued.append((function, *args))

    monkeypatch.setattr(usefulness, "enqueue_best_effort", enqueue)
    monkeypatch.setattr(usefulness.settings.otel, "langfuse_public_key", "pk")
    monkeypatch.setattr(usefulness.settings.otel, "langfuse_secret_key", usefulness.settings.otel.langfuse_secret_key.__class__("sk"))
    context = memory_session()
    session = run_async(context.__aenter__())

    async def seed() -> None:
        """Persist the scenario."""
        session.add_all([Project(title="Big Fish"), Project(title="Other")])
        await session.flush()
        screenplay = Screenplay(project_id=1, title="Big Fish")
        session.add(screenplay)
        await session.flush()
        act = Act(screenplay_id=screenplay.id or 0)
        session.add(act)
        await session.flush()
        scene = Scene(act_id=act.id or 0, heading="INT. HALL")
        session.add(scene)
        await session.flush()
        run = WorkflowRun(project_id=1, kind="room_workflow", status="succeeded", input={"workflow": "rewrite_scene"})
        session.add(run)
        await session.flush()
        four_blocks = {"blocks": [{"text": str(index)} for index in range(4)]}
        session.add_all(
            [
                AgentProposal(project_id=1, run_id=run.id, target_kind="scene", target_id=1, operation=four_blocks, base_version=1, status="approved"),
                AgentProposal(project_id=1, run_id=run.id, target_kind="scene", target_id=1, operation=four_blocks, base_version=1, status="rejected"),
                AgentProposal(project_id=1, run_id=run.id, target_kind="scene", target_id=1, operation=four_blocks, base_version=1, status="proposed"),
                AgentProposal(project_id=1, run_id=None, target_kind="block", target_id=9, operation={"text": "x"}, base_version=1, status="approved"),
            ]
        )
        # Proposal 1 wrote four blocks; the writer has since rewritten one of them (origin back to human).
        session.add_all([Block(scene_id=scene.id or 0, position=index, text=str(index), origin="proposal:1") for index in range(3)])
        session.add(Block(scene_id=scene.id or 0, position=3, text="mine", origin="human"))
        session.add_all(
            [
                AgentRun(project_id=1, workflow_run_id=run.id, role="scene_writer", status="succeeded", input_tokens=900, output_tokens=100, duration_ms=40_000, trace_id="a" * 32),
                AgentRun(project_id=1, workflow_run_id=run.id, role="script_doctor", status="failed", duration_ms=10_000, trace_id="b" * 32),
            ]
        )
        await session.commit()

    run_async(seed())
    app = FastAPI()

    async def dependency() -> AsyncGenerator[AsyncSession]:
        """Yield the shared seeded session."""
        yield session

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(router, prefix="/api/v1")
    yield TestClient(app), session, queued
    run_async(context.__aexit__(None, None, None))


def test_insights_measure_acceptance_retention_and_cost(seeded: tuple[TestClient, AsyncSession, list[Any]]) -> None:
    """Acceptance counts decided proposals; retention counts surviving agent-authored blocks."""
    client, _session, _queued = seeded
    insights = client.get("/api/v1/projects/1/insights").json()
    rewrite = insights["workflows"]["rewrite_scene"]
    assert (rewrite["approved"], rewrite["rejected"], rewrite["pending"]) == (1, 1, 1)
    assert rewrite["acceptance"] == 0.5 and rewrite["retention"] == 0.75 and rewrite["usefulness"] == 0.625
    chat = insights["workflows"][usefulness.CHAT]
    assert chat["approved"] == 1 and chat["retention"] == 0.0  # its block no longer carries the proposal's origin
    assert insights["roles"]["scene_writer"] == {"runs": 1, "failure_rate": 0.0, "tokens": 1000, "mean_duration_s": 40.0}
    assert insights["roles"]["script_doctor"]["failure_rate"] == 1.0
    assert client.get("/api/v1/projects/99/insights").status_code == 404


def test_feedback_is_validated_stored_and_scored(seeded: tuple[TestClient, AsyncSession, list[Any]]) -> None:
    """Exactly one target, a non-zero rating, and the right project; the run's traces get a score."""
    client, _session, queued = seeded
    assert client.post("/api/v1/projects/1/feedback", json={"rating": 1}).status_code == 422
    assert client.post("/api/v1/projects/1/feedback", json={"rating": 0, "workflow_run_id": 1}).status_code == 422
    assert client.post("/api/v1/projects/2/feedback", json={"rating": 1, "workflow_run_id": 1}).status_code == 404
    created = client.post("/api/v1/projects/1/feedback", json={"rating": -1, "workflow_run_id": 1, "comment": "Too talky."})
    assert created.status_code == 201, created.text
    function, scores = queued[-1]
    assert function == "push_langfuse_scores"
    assert sorted(score["trace_id"] for score in scores) == ["a" * 32, "b" * 32]
    assert {score["name"] for score in scores} == {"writer_feedback"} and scores[0]["value"] == -1.0
    insights = client.get("/api/v1/projects/1/insights").json()
    assert insights["workflows"]["rewrite_scene"]["down"] == 1 and insights["workflows"]["rewrite_scene"]["thumbs_up_share"] == 0.0


def test_decisions_score_the_runs_traces(seeded: tuple[TestClient, AsyncSession, list[Any]]) -> None:
    """Approving scores 1, rejecting 0; proposals without a run have no traces to score."""
    _client, session, queued = seeded

    async def decide() -> None:
        """Record the seeded decisions."""
        for proposal_id in (1, 2, 4):
            proposal = await session.get(AgentProposal, proposal_id)
            assert proposal is not None
            await usefulness.record_decision(session, proposal)

    run_async(decide())
    names = [(scores[0]["name"], scores[0]["value"]) for _function, scores in queued]
    assert names == [("proposal_approved", 1.0), ("proposal_rejected", 0.0)]


def test_scores_post_to_langfuse_with_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each score becomes one authenticated POST to the public scores API; failures are skipped."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Accept the first score and reject the second."""
        seen.append(request)
        return httpx.Response(200 if len(seen) == 1 else 500, json={})

    real = httpx.AsyncClient
    monkeypatch.setattr(usefulness.httpx, "AsyncClient", lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(usefulness.settings.otel, "exporter_otlp_endpoint", "http://langfuse-web:3000/api/public/otel")
    monkeypatch.setattr(usefulness.settings.otel, "langfuse_public_key", "pk")
    monkeypatch.setattr(usefulness.settings.otel, "langfuse_secret_key", usefulness.settings.otel.langfuse_secret_key.__class__("sk"))
    scores = [{"trace_id": "a" * 32, "name": "writer_feedback", "value": 1.0, "comment": "Great"}, {"trace_id": "b" * 32, "name": "x", "value": 0.0}]
    assert run_async(usefulness.push_scores(scores)) == 1
    assert str(seen[0].url) == "http://langfuse-web:3000/api/public/scores"
    assert seen[0].headers["authorization"].startswith("Basic ")
    assert json.loads(seen[0].content) == {"traceId": "a" * 32, "name": "writer_feedback", "value": 1.0, "dataType": "NUMERIC", "comment": "Great"}


def test_online_checks_score_real_results() -> None:
    """Workflow results get the offline suites' deterministic checks; unknown workflows get none."""
    scene = {"fountain": "INT. HALL - NIGHT\n\nWill waits.\n\nWILL\nWell?\n", "critique": {"score": 7}}
    assert online_checks("rewrite_scene", scene) == {"valid_scene": 1.0, "critique_score": 0.7}
    assert online_checks("rewrite_scene", {"fountain": "   ", "critique": None}) == {"valid_scene": 0.0, "critique_score": 0.0}
    assert online_checks("continuity", {"issues": [], "dropped": 2}) == {"cites_real_scenes": 0.0}
    assert online_checks("brainstorm", {}) == {}
