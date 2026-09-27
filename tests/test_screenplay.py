"""Tests for the screenplay domain layer: format adapters and revision snapshots."""

import pytest

from draftpilot.core.screenplay.adapters.fdx import parse_fdx, render_fdx
from draftpilot.core.screenplay.adapters.fountain import parse_fountain, render_fountain
from draftpilot.core.screenplay.editor import (
    autocomplete_characters,
    autocomplete_elements,
    dual_dialogue_group,
    next_element,
)
from draftpilot.core.screenplay.html import render_html
from draftpilot.core.screenplay.pdf import render_pdf
from draftpilot.core.screenplay.schema import SceneDoc
from draftpilot.models import Block, DialogueTranslationCreate
from draftpilot.models.enums import BlockType
from draftpilot.models.scene_revision import SceneRevision

SAMPLE = """Title: Test Script
Author: Jane

INT. HOUSE - DAY

A man enters the room.

BOB (V.O.)
Hello there.

BOB
(nervously)
Is anyone home?

CUT TO:

EXT. STREET - NIGHT

Rain falls.
"""


def test_fountain_parse_structure() -> None:
    """Parsing Fountain yields one act with the expected scenes and blocks."""
    doc = parse_fountain(SAMPLE)
    assert doc.title_page["Title"] == "Test Script"
    assert len(doc.acts) == 1
    scenes = doc.acts[0].scenes
    assert [s.heading for s in scenes] == ["INT. HOUSE - DAY", "EXT. STREET - NIGHT"]
    first = scenes[0].blocks
    assert first[0].element_type is BlockType.ACTION
    character = next(b for b in first if b.element_type is BlockType.CHARACTER)
    assert character.text == "BOB"
    assert character.character_extension == "V.O."


def test_fountain_roundtrip_is_idempotent() -> None:
    """Rendering a parsed doc back to Fountain and reparsing reproduces the doc."""
    doc = parse_fountain(SAMPLE)
    assert parse_fountain(render_fountain(doc)) == doc


def test_fdx_preserves_scene_headings() -> None:
    """A doc rendered to FDX and reparsed keeps its scene headings in order.

    The FDX format does not carry Fountain title-page metadata, so it is cleared
    before the round-trip (title-page fidelity is a Fountain-only guarantee).
    """
    doc = parse_fountain(SAMPLE)
    doc.title_page = {}
    reparsed = parse_fdx(render_fdx(doc))
    headings = [s.heading for act in reparsed.acts for s in act.scenes]
    assert headings == ["INT. HOUSE - DAY", "EXT. STREET - NIGHT"]


def test_fdx_parser_rejects_dtd_and_entity_declarations() -> None:
    """Reject XML constructs that can access external resources or expand entities."""
    unsafe = """<?xml version="1.0"?>
<!DOCTYPE FinalDraft [<!ENTITY secret SYSTEM "file:///etc/passwd">]>
<FinalDraft><Content><Paragraph Type="Action"><Text>&secret;</Text></Paragraph></Content></FinalDraft>"""
    with pytest.raises(ValueError, match="DTD or entity"):
        parse_fdx(unsafe)


def test_scene_doc_snapshot_roundtrip() -> None:
    """A SceneDoc survives the snapshot serialization used by scene revisions."""
    scene = parse_fountain(SAMPLE).acts[0].scenes[0]
    restored = SceneDoc.model_validate(scene.model_dump(mode="json"))
    assert restored == scene


def test_pdf_rendering_returns_a_valid_pdf_document() -> None:
    """Render canonical screenplay semantics to a PDF document."""
    document = parse_fountain(SAMPLE)
    rendered = render_pdf(document)
    assert rendered.startswith(b"%PDF-")
    assert len(rendered) > 500


def test_html_rendering_escapes_content_and_preserves_semantics() -> None:
    """Render print-ready HTML without allowing screenplay text to become markup."""
    document = parse_fountain("Title: <Unsafe>\n\nINT. HOUSE - DAY\n\n<script>alert(1)</script>")
    rendered = render_html(document)
    assert "&lt;Unsafe&gt;" in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>alert(1)</script>" not in rendered
    assert 'class="scene-heading"' in rendered


def test_dialogue_translation_keeps_source_block_unchanged() -> None:
    """Store a translation as a linked variant rather than replacing source text."""
    source = Block(id=4, scene_id=2, text="We should go.", element_type=BlockType.DIALOGUE)
    translation = DialogueTranslationCreate(
        block_id=source.id or 0, language="Hindi", text="हमें जाना चाहिए।"
    )
    assert translation.text != source.text
    assert source.text == "We should go."


def test_editor_suggestions_and_tab_transitions_are_typed() -> None:
    """Offer deterministic screenplay element and character suggestions."""
    assert autocomplete_elements("dia") == [BlockType.DIALOGUE]
    assert autocomplete_characters("al", ["ALICE", "ALICE", "BOB"]) == ["ALICE"]
    assert next_element(BlockType.CHARACTER) is BlockType.PARENTHETICAL


def test_dual_dialogue_groups_are_positive_and_new() -> None:
    """Allocate a group that cannot collide with either paired block."""
    assert dual_dialogue_group(4, 7) == 8


def test_revision_snapshot_contains_selectable_scene_sections() -> None:
    """Represent named revision content as independently restorable sections."""
    revision = SceneRevision(
        id=9,
        scene_id=3,
        rev_number=2,
        message="Before the reveal",
        snapshot={"heading": "INT. HOUSE - NIGHT", "blocks": []},
    )
    assert revision.message == "Before the reveal"
    assert set(revision.snapshot) == {"heading", "blocks"}


def test_pdf_renders_the_whole_of_big_fish() -> None:
    """Every scene of a real script renders, including apostrophes, ampersands and angle brackets."""
    from pathlib import Path

    from draftpilot.core.screenplay.adapters.fountain import parse_fountain
    from draftpilot.core.screenplay.pdf import render_pdf

    doc = parse_fountain((Path(__file__).parent / "test_screenplays" / "Big-Fish.fountain").read_text())
    doc.acts[0].scenes[0].heading = "INT. WILL'S & JO'S <FLAT> - NIGHT"
    pdf = render_pdf(doc)
    assert pdf[:4] == b"%PDF" and len(pdf) > 100_000
