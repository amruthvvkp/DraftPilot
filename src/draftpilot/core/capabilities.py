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
    Capability(name="script.analyze", description="Run read-only analysis code and the continuity rules over the script and Story twin in the Monty sandbox.", scope="project"),
    Capability(name="projects.read", description="List the projects this client can work on.", scope="installation"),
    Capability(name="projects.create", description="Create a new project (with its first draft and act).", scope="installation", mutates=True),
    Capability(name="projects.update", description="Edit a project's brief, storyline and settings.", scope="project", mutates=True, approval_required=True),
    Capability(name="projects.duplicate", description="Copy a project into a new one (non-destructive).", scope="project", mutates=True),
    Capability(name="projects.delete", description="Back up and delete a project.", scope="project", mutates=True, approval_required=True),
    Capability(name="story.read", description="Read the storyline, characters, timelines, shared moments, narrative variants, relationships, locations and outline.", scope="project"),
    Capability(name="story.write", description="Create, edit or delete characters, timelines, shared moments, narrative variants, relationships, locations and beats.", scope="project", mutates=True, approval_required=True),
    Capability(name="story.propose", description="Propose story changes (cast, timelines, shared moments, outline, storyline) for the writer to review.", scope="project", mutates=True),
    Capability(name="structure.write", description="Create, edit, move or delete acts, scenes and screenplay blocks.", scope="screenplay", mutates=True, approval_required=True),
    Capability(name="revisions.create", description="Capture a named scene snapshot.", scope="scene", mutates=True),
    Capability(name="imports.create", description="Import a Fountain, FDX or PDF script as a new draft.", scope="project", mutates=True),
    Capability(name="artifacts.write", description="Create, edit or delete story artifacts (briefs, notes, bibles).", scope="artifact", mutates=True, approval_required=True),
    Capability(name="knowledge_graph.write", description="Create, edit or delete canon graph nodes and relationships.", scope="project", mutates=True, approval_required=True),
    Capability(name="twins.refresh", description="Re-derive the Story twin from the working draft.", scope="project"),
    Capability(name="writer.read", description="Read the Writer twin (profile, memories, learned preferences).", scope="project"),
    Capability(name="writer.write", description="Update the writer profile or remember a preference.", scope="project", mutates=True, approval_required=True),
)

_PAGE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "studio": ("outline.read", "story.read", "story.propose", "story.operation", "context.read", "context.generate", "room.workflow", "knowledge_graph.read", "revisions.read"),
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
