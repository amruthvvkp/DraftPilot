"""Project brief and storyline (logline, premise, synopsis, theme, tone, outline) service."""

from typing import Any

from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import events, indexing
from draftpilot.core.errors import Invalid, check_version
from draftpilot.core.story.structure import require_project
from draftpilot.crud import projects as projects_crud
from draftpilot.models import Project, ProjectUpdate, validate_language_separation

STORYLINE_FIELDS = ("title", "logline", "premise", "synopsis", "theme", "tone", "description", "story_outline")


def project_text(project: Project) -> str:
    """Render the project brief and storyline as retrieval text."""
    labelled = (
        ("Title", project.title),
        ("Logline", project.logline),
        ("Premise", project.premise),
        ("Synopsis", project.synopsis),
        ("Theme", project.theme),
        ("Tone", project.tone),
        ("Description", project.description),
        ("Outline", project.story_outline),
        ("Visual style", project.visual_style),
    )
    return "\n".join(f"{label}: {value}" for label, value in labelled if value)


def storyline(project: Project) -> dict[str, Any]:
    """Return the storyline fields of a project."""
    return {"project_id": project.id, "version": project.version, **{name: getattr(project, name) for name in STORYLINE_FIELDS}}


async def update_project(
    session: AsyncSession, project_id: int, changes: ProjectUpdate | dict[str, Any], expected_version: int | None
) -> Project:
    """Update project metadata/storyline when the caller holds the current version."""
    project = await require_project(session, project_id)
    check_version(expected_version, project.version, "Project")
    try:
        data = changes if isinstance(changes, ProjectUpdate) else ProjectUpdate.model_validate(changes)
    except ValidationError as exc:
        raise Invalid(str(exc)) from exc
    values = data.model_dump(exclude_unset=True)
    if "title" in values and not (values["title"] or "").strip():
        raise Invalid("Title cannot be empty")
    try:
        validate_language_separation(
            values.get("primary_language", project.primary_language), values.get("languages", project.languages)
        )
    except ValueError as exc:
        raise Invalid(str(exc)) from exc
    updated = await projects_crud.update(session, project, data)
    await indexing.index_document(project_id, f"project:{project_id}", "project", project_text(updated), updated.version)
    await events.publish(project_id, "project.changed", {"version": updated.version, "fields": sorted(values)})
    return updated
