"""Test the eval harness, evaluators and baselines without a model (the suites themselves run on LM Studio)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from _async import run_async

from draftpilot.core import rag_client
from draftpilot.core.db import session_scope
from draftpilot.evals.baseline import compare, save
from draftpilot.evals.evaluators import (
    FoundPlanted,
    KeepsCast,
    MentionsAny,
    OutlineShape,
    Shorter,
    speakers,
)
from draftpilot.evals.harness import eval_project
from draftpilot.models import KnowledgeNode


def _ctx(output: Any) -> Any:
    """Build the slice of an evaluator context the evaluators read."""
    return SimpleNamespace(output=output)


ORIGINAL = "INT. HALL - NIGHT\n\nWill waits.\n\nWILL\nWhere is he?\n\nSANDRA\nHe'll come.\n"


def test_evaluators_check_what_they_claim() -> None:
    """Each deterministic evaluator passes and fails on the obvious cases."""
    assert MentionsAny(["josephine"], path="reply").evaluate(_ctx({"reply": "Her name is Josephine."})).value
    assert not MentionsAny(["glass", "death"], minimum=2).evaluate(_ctx("a glass eye")).value
    assert speakers(ORIGINAL) == {"WILL", "SANDRA"}
    assert KeepsCast().evaluate(_ctx({"original": ORIGINAL, "fountain": "INT. HALL - NIGHT\n\nWILL\nWell?\n"})).value
    assert not KeepsCast().evaluate(_ctx({"original": ORIGINAL, "fountain": "INT. HALL - NIGHT\n\nKARL\nHello.\n"})).value
    assert Shorter(target=0.5).evaluate(_ctx({"original": "x" * 100, "fountain": "x" * 50})) == 1.0
    assert Shorter(target=0.5).evaluate(_ctx({"original": "x" * 100, "fountain": "x" * 120})) == 0.0
    beats = [{"act": act, "title": "t", "summary": "s"} for act in (1, 1, 2, 2, 2, 3, 3, 3)]
    assert OutlineShape().evaluate(_ctx({"outline": {"beats": beats}})).value
    assert not OutlineShape().evaluate(_ctx({"outline": {"beats": beats[:5]}})).value
    planted = FoundPlanted(kind="timeline", terms=["35"])
    assert planted.evaluate(_ctx({"issues": [{"kind": "character", "description": "Will is 35 here but 17 in 1987."}]})).value
    assert not planted.evaluate(_ctx({"issues": [{"kind": "timeline", "description": "The ring changes hands."}]})).value


def test_the_harness_is_isolated_and_searchable() -> None:
    """The eval project lives in its own database and index, and nothing leaks to a running stack."""

    async def scenario() -> None:
        """Seed, search, and check the Story twin and the side-effect guards."""
        async with eval_project(embeddings=False) as project:
            assert len(project.scenes) == 191 and project.scene(2).heading.startswith("INT.  WILL'S BEDROOM")
            found = await rag_client.search(project.project_id, "witch glass eye", 3, timeout=1)
            assert any("witch" in item["text"].casefold() for item in found["results"])
            async with session_scope() as session:
                from sqlmodel import select

                leads = (await session.exec(select(KnowledgeNode).where(KnowledgeNode.kind == "character"))).all()
                assert {"Edward", "Will"} <= {node.label for node in leads}
            from draftpilot.core import events
            from draftpilot.core.queue import enqueue_best_effort

            await events.publish(project.project_id, "scene.changed", {})  # swallowed, never reaches Redis
            await enqueue_best_effort("index_rag_document", {}, description="eval guard")  # refused, never queued
        assert rag_client._local_index is None

    run_async(scenario())


def test_baselines_flag_drops_beyond_tolerance(tmp_path: Path) -> None:
    """A run that falls below its baseline by more than the tolerance is a regression; within it is fine."""
    baseline = {"suite": "room_qa", "failures": [], "assertion_rate": 0.9, "scores": {"CritiqueImproved": 0.8}}
    save(baseline, tmp_path)
    assert compare({**baseline, "assertion_rate": 0.8}, 0.15, tmp_path) == []
    problems = compare({**baseline, "assertion_rate": 0.6, "scores": {"CritiqueImproved": 0.5}, "failures": ["x"]}, 0.15, tmp_path)
    assert len(problems) == 3
    assert compare({**baseline, "suite": "new_suite"}, 0.15, tmp_path) == []
