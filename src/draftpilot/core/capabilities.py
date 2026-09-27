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
    Capability(name="story.operation", description="Apply a typed story-development operation.", scope="artifact", mutates=True, approval_required=True),
    Capability(name="timeline.propose", description="Calculate a reversible scene reorder proposal.", scope="screenplay"),
    Capability(name="timeline.approve", description="Approve a pending timeline reorder.", scope="screenplay", mutates=True, approval_required=True),
    Capability(name="timeline.rollback", description="Roll back an approved timeline reorder.", scope="screenplay", mutates=True, approval_required=True),
    Capability(name="screenplay.read", description="Read canonical screenplay blocks and versions.", scope="scene"),
    Capability(name="screenplay.propose", description="Create a reviewable typed screenplay change proposal.", scope="scene", mutates=True, approval_required=False),
    Capability(name="screenplay.approve", description="Approve a pending screenplay proposal.", scope="scene", mutates=True, approval_required=True),
    Capability(name="screenplay.rollback", description="Roll back an approved screenplay proposal.", scope="scene", mutates=True, approval_required=True),
    Capability(name="context.read", description="Read scoped project and scene context.", scope="artifact"),
    Capability(name="context.generate", description="Start a cited, review-only context workflow run.", scope="artifact"),
    Capability(name="room.workflow", description="Start a writers' room workflow that ends in reviewable proposals or a report.", scope="project"),
    Capability(name="context.apply", description="Apply an approved context suggestion as a canonical graph node.", scope="artifact", mutates=True, approval_required=True),
    Capability(name="knowledge_graph.read", description="Read project-scoped canon nodes and relationships.", scope="project"),
    Capability(name="copilot.write", description="Persist a context-bearing Copilot conversation turn.", scope="project", mutates=True, approval_required=False),
    Capability(name="translation.propose", description="Propose a linked dialogue translation.", scope="dialogue", approval_required=False),
    Capability(name="revisions.read", description="Read scene revisions and snapshots.", scope="scene"),
    Capability(name="revisions.restore", description="Restore a named scene revision.", scope="scene", mutates=True, approval_required=True),
    Capability(name="evaluations.read", description="Read persisted evaluation results.", scope="project"),
    Capability(name="exports.read", description="Render a screenplay export for download.", scope="project"),
    Capability(name="exports.create", description="Create a screenplay export artifact.", scope="project", mutates=True, approval_required=True),
    Capability(name="providers.read", description="Read redacted provider profiles and availability.", scope="installation"),
    Capability(name="providers.write", description="Create or update an encrypted provider profile.", scope="installation", mutates=True, approval_required=True),
    Capability(name="backups.read", description="List project backup manifests.", scope="project"),
    Capability(name="backups.create", description="Create a project backup artifact.", scope="project", mutates=True, approval_required=True),
    Capability(name="backups.restore", description="Restore a project backup into a new project.", scope="project", mutates=True, approval_required=True),
    Capability(name="runs.read", description="Inspect a project workflow run.", scope="run"),
    Capability(name="runs.control", description="Inspect, pause, resume, or cancel a workflow run.", scope="run", mutates=True, approval_required=True),
    Capability(name="monty.audit.read", description="Read redacted Monty execution audit records.", scope="project"),
)

_PAGE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "studio": ("outline.read", "story.operation", "context.read", "context.generate", "room.workflow", "knowledge_graph.read", "revisions.read"),
    "timeline": ("timeline.propose", "screenplay.read", "context.read", "revisions.read"),
    "review": ("evaluations.read", "screenplay.read", "context.read", "revisions.read", "screenplay.propose", "screenplay.approve", "screenplay.rollback"),
    "exports": ("exports.read", "exports.create", "backups.read", "backups.create", "backups.restore"),
    "settings": ("providers.read", "providers.write", "backups.read", "backups.create", "backups.restore"),
    "context": ("context.read", "context.generate", "context.apply", "knowledge_graph.read", "revisions.read"),
    "workspace": ("screenplay.read", "context.read", "revisions.read"),
}


def capabilities_for_page(page: str) -> list[str]:
    """Return the server-authoritative capability bundle for a workflow page."""
    normalized = page.casefold().strip().strip("/").split("/")[-1] or "workspace"
    return list(_PAGE_CAPABILITIES.get(normalized, _PAGE_CAPABILITIES["workspace"]))


def capability_catalog() -> list[Capability]:
    """Return a copy of the public capability catalog."""
    return [cap.model_copy(deep=True) for cap in CAPABILITIES]
