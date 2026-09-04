"""Fixture-safe benchmark manifests and screenplay comparison reports."""

from collections import Counter
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, Field

from draftpilot.core.screenplay.schema import ScreenplayDoc

BenchmarkTrack = Literal["redevelopment", "import_compare"]


class BenchmarkManifest(BaseModel):
    """Describe one isolated screenplay benchmark project without raw screenplay text."""

    schema_version: int = 1
    track: BenchmarkTrack
    label: str = Field(min_length=1, max_length=200)
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    screenplay_title: str = ""
    primary_language: str = "English"
    translation_languages: list[str] = Field(default_factory=list)
    scene_count: int = Field(default=0, ge=0)
    block_count: int = Field(default=0, ge=0)
    dialogue_count: int = Field(default=0, ge=0)
    dual_dialogue_count: int = Field(default=0, ge=0)
    element_counts: dict[str, int] = Field(default_factory=dict)
    scene_headings: list[str] = Field(default_factory=list)
    runtime_seconds: int = Field(default=0, ge=0)


class BenchmarkComparison(BaseModel):
    """Report structural and multilingual differences between two isolated manifests."""

    control_label: str
    candidate_label: str
    scene_count_delta: int
    block_count_delta: int
    dialogue_count_delta: int
    runtime_seconds_delta: int
    missing_headings: list[str]
    added_headings: list[str]
    primary_language_match: bool
    translation_languages_match: bool
    element_count_deltas: dict[str, int]
    passed: bool


def source_digest(data: bytes) -> str:
    """Return a stable SHA-256 digest for an imported source artifact."""
    return sha256(data).hexdigest()


def manifest_from_document(
    document: ScreenplayDoc,
    *,
    track: BenchmarkTrack,
    label: str,
    primary_language: str = "English",
    translation_languages: list[str] | None = None,
    source_data: bytes | None = None,
    source_sha256: str | None = None,
    runtime_seconds: int = 0,
) -> BenchmarkManifest:
    """Build a benchmark manifest from canonical screenplay semantics."""
    scenes = [scene for act in document.acts for scene in act.scenes]
    blocks = [block for scene in scenes for block in scene.blocks]
    counts = Counter(block.element_type.value for block in blocks)
    return BenchmarkManifest(
        track=track,
        label=label,
        source_sha256=source_sha256 or (source_digest(source_data) if source_data is not None else None),
        screenplay_title=document.title_page.get("Title", ""),
        primary_language=primary_language,
        translation_languages=translation_languages or [],
        scene_count=len(scenes),
        block_count=len(blocks),
        dialogue_count=counts.get("dialogue", 0),
        dual_dialogue_count=sum(block.is_dual for block in blocks),
        element_counts=dict(sorted(counts.items())),
        scene_headings=[scene.heading for scene in scenes],
        runtime_seconds=runtime_seconds,
    )


def compare_manifests(
    control: BenchmarkManifest, candidate: BenchmarkManifest
) -> BenchmarkComparison:
    """Compare two manifests while preserving order-sensitive scene diagnostics."""
    control_elements = control.element_counts
    candidate_elements = candidate.element_counts
    element_deltas = {
        key: candidate_elements.get(key, 0) - control_elements.get(key, 0)
        for key in sorted(set(control_elements) | set(candidate_elements))
    }
    missing = [heading for heading in control.scene_headings if heading not in candidate.scene_headings]
    added = [heading for heading in candidate.scene_headings if heading not in control.scene_headings]
    primary_match = control.primary_language.casefold() == candidate.primary_language.casefold()
    translations_match = {
        language.casefold() for language in control.translation_languages
    } == {language.casefold() for language in candidate.translation_languages}
    return BenchmarkComparison(
        control_label=control.label,
        candidate_label=candidate.label,
        scene_count_delta=candidate.scene_count - control.scene_count,
        block_count_delta=candidate.block_count - control.block_count,
        dialogue_count_delta=candidate.dialogue_count - control.dialogue_count,
        runtime_seconds_delta=candidate.runtime_seconds - control.runtime_seconds,
        missing_headings=missing,
        added_headings=added,
        primary_language_match=primary_match,
        translation_languages_match=translations_match,
        element_count_deltas=element_deltas,
        passed=not (missing or added or not primary_match or not translations_match),
    )
