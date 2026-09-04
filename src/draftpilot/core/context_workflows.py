"""Typed contracts for reusable creative-context generation workflows."""

from typing import Literal

from pydantic import BaseModel, Field

from draftpilot.core.agent_roles import AgentRoleKey, PermissionMode


class ContextWorkflowSpec(BaseModel):
    """Describe one context-generation workflow and its review contract."""

    key: str
    label: str
    description: str
    input_artifact_kinds: tuple[str, ...]
    output_kind: str
    evaluator: str
    agent_role: AgentRoleKey
    permission_mode: PermissionMode = "suggest"


CONTEXT_WORKFLOWS: tuple[ContextWorkflowSpec, ...] = (
    ContextWorkflowSpec(
        key="reference_scene",
        label="Reference scene",
        description="Extract usable staging, rhythm, and visual cues from a reference scene.",
        input_artifact_kinds=("brief", "outline", "character", "canon"),
        output_kind="reference_scene",
        evaluator="continuity_review",
        agent_role="researcher",
    ),
    ContextWorkflowSpec(
        key="visual_language",
        label="Visual language",
        description="Propose a coherent visual grammar for the project.",
        input_artifact_kinds=("brief", "outline", "canon"),
        output_kind="style",
        evaluator="visual_consistency_review",
        agent_role="associate_director",
    ),
    ContextWorkflowSpec(
        key="camera",
        label="Camera plan",
        description="Suggest camera grammar, lenses, movement, and coverage principles.",
        input_artifact_kinds=("brief", "outline", "timeline"),
        output_kind="camera",
        evaluator="production_feasibility_review",
        agent_role="associate_director",
    ),
    ContextWorkflowSpec(
        key="lighting",
        label="Lighting plan",
        description="Develop lighting intent that supports the story and visual language.",
        input_artifact_kinds=("brief", "outline", "style"),
        output_kind="lighting",
        evaluator="visual_consistency_review",
        agent_role="associate_director",
    ),
    ContextWorkflowSpec(
        key="color_palette",
        label="Color palette",
        description="Propose a scene-aware palette with emotional and continuity rationale.",
        input_artifact_kinds=("brief", "outline", "style", "reference_scene"),
        output_kind="color_palette",
        evaluator="visual_consistency_review",
        agent_role="associate_director",
    ),
    ContextWorkflowSpec(
        key="film_director_style",
        label="Film, director, and style research",
        description="Turn project references into bounded, citable creative-context notes.",
        input_artifact_kinds=("brief", "outline", "reference"),
        output_kind="film",
        evaluator="research_quality_review",
        agent_role="researcher",
    ),
    ContextWorkflowSpec(
        key="continuity",
        label="Continuity pass",
        description="Find continuity risks across canon, characters, timeline, and screenplay.",
        input_artifact_kinds=("brief", "outline", "character", "timeline", "canon"),
        output_kind="canon",
        evaluator="continuity_review",
        agent_role="continuity_supervisor",
    ),
)

WorkflowPermission = Literal["suggest", "scoped_edit", "project_edit"]


def context_workflow_catalog() -> list[ContextWorkflowSpec]:
    """Return independent copies of the context workflow catalog."""
    return [workflow.model_copy(deep=True) for workflow in CONTEXT_WORKFLOWS]


def get_context_workflow(key: str) -> ContextWorkflowSpec | None:
    """Return one named context workflow or ``None`` when unknown."""
    return next((workflow for workflow in CONTEXT_WORKFLOWS if workflow.key == key), None)


class ContextWorkflowRequest(BaseModel):
    """Describe a provider-backed context workflow run."""

    workflow: str = Field(min_length=1, max_length=80)
    artifact_id: int | None = Field(default=None, ge=1)
    instruction: str = Field(min_length=1, max_length=12_000)
    permission_mode: WorkflowPermission = "suggest"
