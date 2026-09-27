"""Built-in agent role and permission contracts."""

from typing import Literal

from pydantic import BaseModel

PermissionMode = Literal["chat_only", "suggest", "scoped_edit", "project_edit"]
AgentRoleKey = Literal[
    "showrunner",
    "story_architect",
    "story_editor",
    "brainstormer",
    "scene_writer",
    "script_doctor",
    "coverage_reader",
    "researcher",
    "character_specialist",
    "script_editor",
    "continuity_supervisor",
    "associate_director",
    "audience_evaluator",
]


class AgentRole(BaseModel):
    """Describe one built-in creative agent role."""

    key: AgentRoleKey
    label: str
    description: str
    default_permission: PermissionMode = "chat_only"


AGENT_ROLES: tuple[AgentRole, ...] = (
    AgentRole(key="showrunner", label="Showrunner", description="Run the room: plan, consult specialists, and bring back one clear answer."),
    AgentRole(key="story_architect", label="Story architect", description="Shape premise, structure, causality, and thematic arcs."),
    AgentRole(key="story_editor", label="Story editor", description="Build and repair outlines, beat sheets, and pacing across acts."),
    AgentRole(key="brainstormer", label="Brainstormer", description="Generate divergent premises, twists, set pieces, and alternatives."),
    AgentRole(key="scene_writer", label="Scene writer", description="Draft and redraft scenes from beats in the writer's voice."),
    AgentRole(key="script_doctor", label="Script doctor", description="Diagnose what is not working and prescribe targeted rewrites."),
    AgentRole(key="coverage_reader", label="Coverage reader", description="Write studio-style coverage with graded craft and a verdict."),
    AgentRole(key="researcher", label="Researcher", description="Find and cite project-relevant research context."),
    AgentRole(key="character_specialist", label="Character specialist", description="Develop character wants, needs, arcs, and relationships."),
    AgentRole(key="script_editor", label="Script editor", description="Review screenplay craft, clarity, rhythm, and formatting."),
    AgentRole(key="continuity_supervisor", label="Continuity supervisor", description="Check timeline, canon, props, locations, and character continuity."),
    AgentRole(key="associate_director", label="Associate director", description="Develop staging, camera, lighting, and production-facing context."),
    AgentRole(key="audience_evaluator", label="Audience evaluator", description="Evaluate audience clarity, tone, pacing, and emotional impact."),
)

AGENT_ROLE_KEYS = frozenset(role.key for role in AGENT_ROLES)


def normalize_agent_role(value: object) -> AgentRoleKey:
    """Return a catalog role key, falling back to the default role."""
    return value if isinstance(value, str) and value in AGENT_ROLE_KEYS else "story_architect"  # type: ignore[return-value]


def normalize_permission_mode(value: object) -> PermissionMode:
    """Return a supported permission mode, falling back to chat-only."""
    allowed = {"chat_only", "suggest", "scoped_edit", "project_edit"}
    return value if isinstance(value, str) and value in allowed else "chat_only"  # type: ignore[return-value]


def agent_roles() -> list[AgentRole]:
    """Return independent copies of the built-in role catalog."""
    return [role.model_copy(deep=True) for role in AGENT_ROLES]
