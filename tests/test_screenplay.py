"""Tests for the screenplay domain layer: format adapters and revision snapshots."""

from draftpilot.core.screenplay.adapters.fdx import parse_fdx, render_fdx
from draftpilot.core.screenplay.adapters.fountain import parse_fountain, render_fountain
from draftpilot.core.screenplay.schema import SceneDoc
from draftpilot.models.enums import BlockType

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


def test_scene_doc_snapshot_roundtrip() -> None:
    """A SceneDoc survives the snapshot serialization used by scene revisions."""
    scene = parse_fountain(SAMPLE).acts[0].scenes[0]
    restored = SceneDoc.model_validate(scene.model_dump(mode="json"))
    assert restored == scene
