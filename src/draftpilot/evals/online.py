"""Online checks: the offline suites' deterministic evaluators, run on every real room workflow result."""

from types import SimpleNamespace
from typing import Any

from pydantic_evals.evaluators import EvaluationReason, Evaluator

from draftpilot.evals.evaluators import (
    CritiqueImproved,
    NoHallucinatedScenes,
    OutlineShape,
    ValidScene,
)

CHECKS: dict[str, dict[str, Evaluator[Any, Any, Any]]] = {
    "notes_to_outline": {"outline_shape": OutlineShape(), "critique_score": CritiqueImproved()},
    "rewrite_scene": {"valid_scene": ValidScene(), "critique_score": CritiqueImproved()},
    "continuity": {"cites_real_scenes": NoHallucinatedScenes()},
}


def online_checks(workflow: str, result: dict[str, Any]) -> dict[str, float]:
    """Return each applicable check as a 0-1 score (assertions become 1.0 or 0.0)."""
    scores: dict[str, float] = {}
    for name, evaluator in CHECKS.get(workflow, {}).items():
        try:
            outcome = evaluator.evaluate(SimpleNamespace(output=result))  # type: ignore[arg-type]
        except (KeyError, TypeError, ValueError):
            continue
        value = outcome.value if isinstance(outcome, EvaluationReason) else outcome
        if isinstance(value, bool | int | float):
            scores[name] = float(value)
    return scores
