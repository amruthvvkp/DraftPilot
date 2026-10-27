"""Test fixture-safe screenplay benchmark manifests and comparisons."""

import pytest

from draftpilot.core.benchmark import (
    compare_manifests,
    manifest_from_document,
    source_digest,
)
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


def test_comparison_passes_for_identical_multiscene_screenplay() -> None:
    """Verify that identical multi-scene manifests pass all comparison gates."""
    fountain_text = (
        "INT. ROOM - DAY\n\nALICE\nHello.\n\n"
        "EXT. PARK - NIGHT\n\nBOB\nGoodbye.\n"
    )
    doc = parse_fountain(fountain_text)
    control = manifest_from_document(
        doc,
        track="redevelopment",
        label="control",
        primary_language="English",
        translation_languages=["Spanish"],
        runtime_seconds=120,
    )
    candidate = manifest_from_document(
        doc,
        track="redevelopment",
        label="candidate",
        primary_language="English",
        translation_languages=["Spanish"],
        runtime_seconds=120,
    )
    report = compare_manifests(control, candidate)
    assert report.passed is True
    assert report.scene_count_delta == 0
    assert report.block_count_delta == 0
    assert report.dialogue_count_delta == 0
    assert report.runtime_seconds_delta == 0
    assert report.missing_headings == []
    assert report.added_headings == []
    assert report.primary_language_match is True
    assert report.translation_languages_match is True


def test_benchmark_compare_script_with_fixtures(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI comparison runner against fixture files."""
    import json
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from scripts import benchmark_compare

    fixtures_dir = Path(__file__).parent / "fixtures" / "benchmark"
    control_path = fixtures_dir / "feature_control_manifest.json"
    match_path = fixtures_dir / "feature_candidate_match.json"
    divergent_path = fixtures_dir / "feature_candidate_divergent.json"

    # Test matching run
    monkeypatch.setattr(sys, "argv", ["benchmark_compare.py", str(control_path), str(match_path)])
    benchmark_compare.main()
    captured = capsys.readouterr()
    report_match = json.loads(captured.out)
    assert report_match["passed"] is True
    assert report_match["scene_count_delta"] == 0

    # Test divergent run
    monkeypatch.setattr(sys, "argv", ["benchmark_compare.py", str(control_path), str(divergent_path)])
    benchmark_compare.main()
    captured = capsys.readouterr()
    report_divergent = json.loads(captured.out)
    assert report_divergent["passed"] is False
    assert report_divergent["scene_count_delta"] == -1
    assert "EXT. CANYON RUNWAY - DAY" in report_divergent["missing_headings"]


