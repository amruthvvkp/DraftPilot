"""Typed capability catalog shared by UI agents and external MCP clients."""

from pydantic import BaseModel


class Capability(BaseModel):
    """Describe one scoped DraftPilot capability and its mutation policy."""

    name: str
    description: str
    scope: str
    mutates: bool = False
    approval_required: bool = False


CAPABILITIES: tuple[Capability, ...] = (
    Capability(name="outline.read", description="Read the project brief and outline.", scope="project"),
    Capability(name="timeline.propose", description="Calculate a reversible scene reorder proposal.", scope="screenplay"),
    Capability(name="screenplay.read", description="Read canonical screenplay blocks and versions.", scope="scene"),
    Capability(name="context.read", description="Read scoped project and scene context.", scope="artifact"),
    Capability(name="knowledge_graph.read", description="Read project-scoped canon nodes and relationships.", scope="project"),
    Capability(name="copilot.write", description="Persist a context-bearing Copilot conversation turn.", scope="project", mutates=True, approval_required=False),
    Capability(name="translation.propose", description="Propose a linked dialogue translation.", scope="dialogue", approval_required=True),
    Capability(name="revisions.read", description="Read scene revisions and snapshots.", scope="scene"),
    Capability(name="revisions.restore", description="Restore a named scene revision.", scope="scene", mutates=True, approval_required=True),
    Capability(name="evaluations.read", description="Read persisted evaluation results.", scope="project"),
    Capability(name="exports.create", description="Create a screenplay export artifact.", scope="project", mutates=True, approval_required=True),
    Capability(name="backups.create", description="Create a project backup artifact.", scope="project", mutates=True, approval_required=True),
    Capability(name="runs.control", description="Inspect, pause, resume, or cancel a workflow run.", scope="run", mutates=True, approval_required=True),
)


def capability_catalog() -> list[Capability]:
    """Return a copy of the public capability catalog."""
    return [cap.model_copy(deep=True) for cap in CAPABILITIES]
