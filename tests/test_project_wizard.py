"""Tests for project-wizard payload normalization."""

from draftpilot.models import ReferenceKind, ScreeningType
from draftpilot.ui.project_wizard import (
    ProjectReferenceDraft,
    ProjectWizardData,
    build_project_create,
    reference_create_payloads,
)


def test_build_project_create_normalizes_optional_values_and_lists() -> None:
    """Build a project payload with trimmed values and unique metadata."""
    data = ProjectWizardData(
        title="  The Long Night  ",
        description="  A contained thriller. ",
        genres=["Thriller", " thriller ", ""],
        languages=["English", " English "],
        story_outline="  Three strangers wait out a storm. ",
        screening_type=ScreeningType.FLAT_1_85,
    )

    payload = build_project_create(data)

    assert payload.title == "The Long Night"
    assert payload.description == "A contained thriller."
    assert payload.genres == ["Thriller"]
    assert payload.languages == ["English"]
    assert payload.story_outline == "Three strangers wait out a storm."
    assert payload.screening_type is ScreeningType.FLAT_1_85


def test_project_wizard_keeps_typed_non_empty_references() -> None:
    """Discard empty reference rows while preserving typed creative links."""
    data = ProjectWizardData(
        title="The Long Night",
        references=[
            ProjectReferenceDraft(
                kind=ReferenceKind.FILM, label="  Blue Ruin ", url=" https://film.test "
            ),
            ProjectReferenceDraft(kind=ReferenceKind.OTHER, label=" "),
        ],
    )

    references = reference_create_payloads(7, data)

    assert references[0].project_id == 7
    assert references[0].kind is ReferenceKind.FILM
    assert references[0].label == "Blue Ruin"
    assert references[0].url == "https://film.test"
    assert len(references) == 1
