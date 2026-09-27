"""Deterministic evaluators for the room's outputs; the LLM judge covers what these cannot."""

from dataclasses import dataclass, field
from typing import Any

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from draftpilot.core.scene_proposals import parse_scene_fountain
from draftpilot.core.screenplay.schema import BlockType
from draftpilot.core.twins import normalize_cue


def _text(value: Any) -> str:
    """Flatten an output (string, model, or JSON) into searchable lower-case text."""
    if hasattr(value, "model_dump_json"):
        return str(value.model_dump_json()).casefold()
    return str(value).casefold()


@dataclass
class MentionsAny(Evaluator[Any, Any, Any]):
    """Pass when the output (or one of its fields) mentions at least ``minimum`` of the terms."""

    terms: list[str]
    minimum: int = 1
    path: str = ""

    def evaluate(self, ctx: EvaluatorContext[Any, Any, Any]) -> EvaluationReason:
        """Count the terms that appear."""
        value = ctx.output.get(self.path, "") if self.path and isinstance(ctx.output, dict) else ctx.output
        text = _text(value)
        found = [term for term in self.terms if term.casefold() in text]
        return EvaluationReason(len(found) >= self.minimum, f"found {found} of {self.terms}")


@dataclass
class UsedTools(Evaluator[Any, Any, Any]):
    """Pass when the agent called at least one of ``any_of`` (proof it read the project)."""

    any_of: list[str] = field(default_factory=lambda: ["read_project_overview", "read_screenplay_scenes", "retrieve_project_context", "read_story_twin"])

    def evaluate(self, ctx: EvaluatorContext[Any, Any, Any]) -> EvaluationReason:
        """Check the recorded tool calls."""
        tools = ctx.attributes.get("tools") or (ctx.output.get("tools", []) if isinstance(ctx.output, dict) else [])
        return EvaluationReason(any(tool in tools for tool in self.any_of), f"tools={tools}")


@dataclass
class ValidScene(Evaluator[Any, Any, Any]):
    """Pass when ``output['fountain']`` parses as one screenplay scene with dialogue or action."""

    def evaluate(self, ctx: EvaluatorContext[Any, Any, Any]) -> EvaluationReason:
        """Parse the rewrite."""
        try:
            doc = parse_scene_fountain(ctx.output["fountain"])
        except (KeyError, ValueError) as exc:
            return EvaluationReason(False, str(exc))
        return EvaluationReason(bool(doc.heading) and len(doc.blocks) >= 2, f"heading={doc.heading!r} blocks={len(doc.blocks)}")


def speakers(fountain: str) -> set[str]:
    """Return the normalised character cues in a Fountain scene."""
    doc = parse_scene_fountain(fountain)
    return {normalize_cue(block.text) for block in doc.blocks if block.element_type == BlockType.CHARACTER}


@dataclass
class KeepsCast(Evaluator[Any, Any, Any]):
    """Pass when a rewrite introduces no speaking characters the original did not have."""

    def evaluate(self, ctx: EvaluatorContext[Any, Any, Any]) -> EvaluationReason:
        """Compare speaking casts."""
        before, after = speakers(ctx.output["original"]), speakers(ctx.output["fountain"])
        brief = str(ctx.output.get("brief", "")).upper()
        added = sorted(name for name in after - before if name not in brief)  # characters the brief names may speak
        return EvaluationReason(not added, f"added speakers: {added}" if added else f"cast kept: {sorted(after)}")


@dataclass
class Shorter(Evaluator[Any, Any, Any]):
    """Score how much shorter a rewrite is (1.0 means at most ``target`` of the original length)."""

    target: float = 0.8

    def evaluate(self, ctx: EvaluatorContext[Any, Any, Any]) -> float:
        """Return the length score."""
        ratio = len(ctx.output["fountain"]) / max(1, len(ctx.output["original"]))
        return round(min(1.0, max(0.0, (1 - ratio) / (1 - self.target))), 3)


@dataclass
class OutlineShape(Evaluator[Any, Any, Any]):
    """Pass when an outline has a sane beat count and covers three acts."""

    min_beats: int = 8
    max_beats: int = 40

    def evaluate(self, ctx: EvaluatorContext[Any, Any, Any]) -> EvaluationReason:
        """Check the beat count and act coverage."""
        beats = ctx.output["outline"]["beats"]
        acts = {beat["act"] for beat in beats}
        ok = self.min_beats <= len(beats) <= self.max_beats and {1, 2, 3} <= acts
        return EvaluationReason(ok, f"{len(beats)} beats across acts {sorted(acts)}")


@dataclass
class CritiqueImproved(Evaluator[Any, Any, Any]):
    """Report the final critique score (0-1) so baselines track draft quality over time."""

    def evaluate(self, ctx: EvaluatorContext[Any, Any, Any]) -> float:
        """Normalise the script doctor's last score."""
        critique = ctx.output.get("critique") or {}
        return round(float(critique.get("score", 0)) / 10, 2)


@dataclass
class FoundPlanted(Evaluator[Any, Any, Any]):
    """Pass when a continuity report catches the planted error (by kind and a telltale term)."""

    kind: str
    terms: list[str]

    def evaluate(self, ctx: EvaluatorContext[Any, Any, Any]) -> EvaluationReason:
        """Look for an issue matching the plant."""
        for issue in ctx.output.get("issues", []):
            if any(term.casefold() in _text(issue) for term in self.terms):
                kind = "as expected" if issue.get("kind") == self.kind else f"as {issue.get('kind')}"
                return EvaluationReason(True, f"caught ({kind}): {issue.get('description', '')}")
        return EvaluationReason(False, f"{len(ctx.output.get('issues', []))} issues, none about {self.terms}")


@dataclass
class NoHallucinatedScenes(Evaluator[Any, Any, Any]):
    """Pass when the continuity supervisor cited only real scenes."""

    def evaluate(self, ctx: EvaluatorContext[Any, Any, Any]) -> EvaluationReason:
        """Check the dropped-issue count."""
        dropped = int(ctx.output.get("dropped", 0))
        return EvaluationReason(dropped == 0, f"{dropped} issues cited scenes outside the draft")
