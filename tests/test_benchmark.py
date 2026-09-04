"""Test fixture-safe screenplay benchmark manifests and comparisons."""

from draftpilot.core.benchmark import compare_manifests, manifest_from_document, source_digest
from draftpilot.core.screenplay.adapters.fountain import parse_fountain


def test_manifest_counts_structure_and_source_digest() -> None:
    """Summarize canonical screenplay structure without storing source text."""
    document = parse_fountain("Title: Control\n\nINT. HOUSE - DAY\n\nA door opens.\n\nBOB (V.O.)\nHello.")
    manifest = manifest_from_document(
        document,
        track="import_compare",
        label="control",
        primary_language="Hindi",
        translation_languages=["English"],
        source_data=b"original fdx",
        runtime_seconds=45,
    )

    assert manifest.scene_count == 1
    assert manifest.dialogue_count == 1
    assert manifest.source_sha256 == source_digest(b"original fdx")
    assert "original fdx" not in manifest.model_dump_json()


def test_comparison_reports_order_and_language_differences() -> None:
    """Flag missing/added scenes and multilingual metadata drift."""
    control = manifest_from_document(
        parse_fountain("INT. HOUSE - DAY\n\nAction."),
        track="import_compare",
        label="control",
        primary_language="Hindi",
        translation_languages=["English"],
    )
    candidate = manifest_from_document(
        parse_fountain("INT. STREET - NIGHT\n\nAction."),
        track="import_compare",
        label="candidate",
        primary_language="English",
        translation_languages=[],
    )

    report = compare_manifests(control, candidate)

    assert report.passed is False
    assert report.missing_headings == ["INT. HOUSE - DAY"]
    assert report.added_headings == ["INT. STREET - NIGHT"]
    assert report.primary_language_match is False
    assert report.translation_languages_match is False
