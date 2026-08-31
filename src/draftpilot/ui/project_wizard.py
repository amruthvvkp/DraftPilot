"""Pure payload helpers for the multi-step project creation wizard."""

from pydantic import BaseModel, Field, field_validator

from draftpilot.models import (
    ProjectCreate,
    ProjectReferenceCreate,
    ReferenceKind,
    ScreeningType,
)


class ProjectReferenceDraft(BaseModel):
    """Capture one typed creative reference before a project is saved."""

    kind: ReferenceKind = ReferenceKind.OTHER
    label: str = ""
    url: str | None = None
    note: str | None = None

    @field_validator("label", "url", "note", mode="before")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        """Trim form whitespace while retaining missing optional values."""
        if value is None:
            return None
        return value.strip()


class ProjectWizardData(BaseModel):
    """Represent all values collected by the project creation wizard."""

    title: str = ""
    logline: str | None = None
    description: str | None = None
    genres: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    story_outline: str | None = None
    visual_style: str | None = None
    camera_type: str | None = None
    screening_type: ScreeningType | None = None
    artwork_url: str | None = None
    artwork_path: str | None = None
    references: list[ProjectReferenceDraft] = Field(default_factory=list)

    @field_validator(
        "title",
        "logline",
        "description",
        "story_outline",
        "visual_style",
        "camera_type",
        "artwork_url",
        "artwork_path",
        mode="before",
    )
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        """Trim wizard text values and turn blank strings into missing values."""
        if value is None:
            return None
        value = value.strip()
        return value or None


def _unique_text(values: list[str]) -> list[str]:
    """Return non-empty text values once, preserving their first-seen order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            result.append(cleaned)
            seen.add(key)
    return result


def build_project_create(data: ProjectWizardData) -> ProjectCreate:
    """Convert wizard values into the persisted project payload."""
    return ProjectCreate(
        title=(data.title or "").strip(),
        logline=data.logline,
        description=data.description,
        genres=_unique_text(data.genres),
        languages=_unique_text(data.languages),
        story_outline=data.story_outline,
        visual_style=data.visual_style,
        camera_type=data.camera_type,
        screening_type=data.screening_type,
        artwork_url=data.artwork_url,
        artwork_path=data.artwork_path,
    )


def reference_create_payloads(
    project_id: int, data: ProjectWizardData
) -> list[ProjectReferenceCreate]:
    """Convert non-empty wizard references into persistence payloads."""
    return [
        ProjectReferenceCreate(
            project_id=project_id,
            kind=reference.kind,
            label=reference.label,
            url=reference.url,
            note=reference.note,
        )
        for reference in data.references
        if reference.label
    ]
