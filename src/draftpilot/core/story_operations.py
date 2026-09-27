"""Typed, versioned story-development operations over editable artifacts."""

from copy import deepcopy
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from draftpilot.models import StoryArtifact


class SetLoglineOperation(BaseModel):
    """Replace the canonical brief logline."""

    operation: Literal["set_logline"] = "set_logline"
    text: str = Field(min_length=1, max_length=500)


class AddBeatOperation(BaseModel):
    """Append one causally ordered story beat."""

    operation: Literal["add_beat"] = "add_beat"
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=4000)
    sequence: int = Field(ge=1)
    causal_predecessor_ids: list[str] = Field(default_factory=list, max_length=50)


class AddCharacterArcOperation(BaseModel):
    """Append one character arc decision to a character artifact."""

    operation: Literal["add_character_arc"] = "add_character_arc"
    character: str = Field(min_length=1, max_length=200)
    want: str = Field(min_length=1, max_length=2000)
    need: str = Field(min_length=1, max_length=2000)
    turning_points: list[str] = Field(default_factory=list, max_length=30)


class AddCanonRuleOperation(BaseModel):
    """Append one explicit story-canon rule."""

    operation: Literal["add_canon_rule"] = "add_canon_rule"
    rule: str = Field(min_length=1, max_length=2000)
    rationale: str | None = Field(default=None, max_length=2000)


StoryOperation = Annotated[
    SetLoglineOperation
    | AddBeatOperation
    | AddCharacterArcOperation
    | AddCanonRuleOperation,
    Field(discriminator="operation"),
]


def validate_story_operation(
    artifact_kind: str, operation: str, payload: dict[str, object]
) -> StoryOperation:
    """Validate one operation against its artifact kind and typed payload."""
    operation_models: dict[str, type[BaseModel]] = {
        "set_logline": SetLoglineOperation,
        "add_beat": AddBeatOperation,
        "add_character_arc": AddCharacterArcOperation,
        "add_canon_rule": AddCanonRuleOperation,
    }
    model = operation_models.get(operation)
    if model is None:
        raise ValueError("Unknown story operation")
    parsed = model.model_validate({"operation": operation, **payload})
    allowed_kinds = {
        "set_logline": {"brief"},
        "add_beat": {"outline", "timeline"},
        "add_character_arc": {"character"},
        "add_canon_rule": {"canon"},
    }
    if artifact_kind not in allowed_kinds[operation]:
        raise ValueError(f"{operation} is not valid for a {artifact_kind} artifact")
    return parsed  # type: ignore[return-value]


def apply_story_operation(
    artifact: StoryArtifact, operation: StoryOperation
) -> StoryArtifact:
    """Apply one validated operation without replacing unrelated artifact data."""
    metadata = deepcopy(artifact.artifact_metadata)
    history = list(metadata.get("operations", []))
    history.append(operation.model_dump(mode="json"))
    metadata["operations"] = history
    if isinstance(operation, SetLoglineOperation):
        artifact.content = operation.text
    elif isinstance(operation, AddBeatOperation):
        beats = list(metadata.get("beats", []))
        beats.append(operation.model_dump(mode="json"))
        metadata["beats"] = sorted(beats, key=lambda item: item["sequence"])
    elif isinstance(operation, AddCharacterArcOperation):
        arcs = list(metadata.get("character_arcs", []))
        arcs.append(operation.model_dump(mode="json"))
        metadata["character_arcs"] = arcs
    else:
        rules = list(metadata.get("canon_rules", []))
        rules.append(operation.model_dump(mode="json"))
        metadata["canon_rules"] = rules
    artifact.artifact_metadata = metadata
    artifact.version += 1
    artifact.stale = False
    return artifact
