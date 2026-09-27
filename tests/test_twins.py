"""Test the Story twin (derived from Big Fish) and the Writer twin brief."""

from pathlib import Path

import pytest
from _async import run_async
from _db import memory_session
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.screenplay.adapters.fountain import parse_fountain
from draftpilot.core.screenplay.hydrate import save_screenplay_doc
from draftpilot.core.twins import (
    extract_story_twin,
    normalize_cue,
    parse_heading,
    refresh_story_twin,
    story_twin_brief,
    writer_twin_brief,
)
from draftpilot.crud import blocks as blocks_crud
from draftpilot.crud import knowledge_graph as graph_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.models import (
    AgentProposal,
    Project,
    Screenplay,
    WriterMemory,
    WriterProfile,
)

BIG_FISH = Path(__file__).parent / "test_screenplays" / "Big-Fish.fountain"


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("INT.  WILL'S BEDROOM - NIGHT (1973)", ("INT", "WILL'S BEDROOM", "NIGHT")),
        ("EXT. RIVER - DAY", ("EXT", "RIVER", "DAY")),
        ("INT./EXT. CHEVY - MOVING - DAY", ("INT./EXT", "CHEVY - MOVING", "DAY")),
        ("EXT. SPECTRE", ("EXT", "SPECTRE", None)),
        ("EXT.  BLOOM BACK YARD - NIGHT [CONTINUOUS]", ("EXT", "BLOOM BACK YARD", "NIGHT")),
        ("INT./EXT.  BLOOM HOUSE - (PRESENT) DAY", ("INT./EXT", "BLOOM HOUSE", "DAY")),
        ("A dream", (None, None, None)),
    ],
)
def test_scene_headings_split_into_int_ext_location_and_time(heading: str, expected: tuple[object, ...]) -> None:
    """Standard and unusual headings parse into their parts."""
    parsed = parse_heading(heading)
    assert (parsed.int_ext, parsed.location, parsed.time) == expected


def test_character_cues_drop_extensions() -> None:
    """Cues normalise to one name regardless of V.O./CONT'D extensions."""
    assert normalize_cue("Edward (V.O.)") == normalize_cue("EDWARD (CONT'D)") == "EDWARD"


async def _big_fish(session: AsyncSession) -> int:
    """Import Big Fish into a new project and return its id."""
    project = Project(title="Big Fish")
    session.add(project)
    await session.flush()
    screenplay = Screenplay(project_id=project.id or 0, title="Big Fish")
    session.add(screenplay)
    await session.commit()
    await save_screenplay_doc(session, screenplay.id or 0, parse_fountain(BIG_FISH.read_text()))
    return project.id or 0


def test_story_twin_is_derived_from_the_big_fish_script() -> None:
    """Edward and Will lead the cast; the Bloom house and river are key locations."""

    async def scenario() -> None:
        """Extract the twin from the imported script."""
        async with memory_session() as session:
            await _big_fish(session)
            scenes = await scenes_crud.list_for_screenplay(session, 1)
            blocks = await blocks_crud.list_for_scenes(session, [scene.id or 0 for scene in scenes])
            characters, locations = extract_story_twin(scenes, blocks)
            leads = [character.name for character in characters[:4]]
            assert "EDWARD" in leads and "WILL" in leads
            assert all(character.dialogue_lines > 0 for character in characters)
            top = [location.name for location in locations[:10]]
            assert "HOSPITAL ROOM" in top[:5] and "BLOOM HOUSE" in top[:5]
            bloom = next(location for location in locations if location.name == "BLOOM HOUSE")
            assert bloom.times >= {"DAY", "NIGHT"} and "INT./EXT" in bloom.int_ext
            edward = next(character for character in characters if character.name == "EDWARD")
            assert edward.first_scene_id == edward.scene_ids[0]

    run_async(scenario())


def test_twin_keeper_is_idempotent_and_never_overwrites_the_writer() -> None:
    """Refreshing twice changes nothing; a writer-edited node keeps the writer's description."""

    async def scenario() -> None:
        """Refresh, edit one node as the writer, refresh again."""
        async with memory_session() as session:
            project_id = await _big_fish(session)
            first = await refresh_story_twin(session, project_id)
            assert first["characters"] > 20 and first["locations"] > 20
            nodes = await graph_crud.list_nodes(session, project_id)
            versions = {node.id: node.version for node in nodes}
            again = await refresh_story_twin(session, project_id)
            assert again == {**first, "removed": 0}
            assert {node.id: node.version for node in await graph_crud.list_nodes(session, project_id)} == versions
            edward = next(node for node in nodes if node.kind == "character" and node.label == "Edward")
            edward.description = "A storyteller whose tall tales hide his truth."
            edward.node_metadata = {**edward.node_metadata, "writer_edited": True}
            session.add(edward)
            await session.commit()
            await refresh_story_twin(session, project_id)
            refreshed = next(node for node in await graph_crud.list_nodes(session, project_id) if node.id == edward.id)
            assert refreshed.description == "A storyteller whose tall tales hide his truth."
            brief = await story_twin_brief(session, project_id)
            assert "Edward" in brief and "A storyteller" in brief and "Key locations:" in brief

    run_async(scenario())


def test_writer_brief_carries_profile_memories_and_learned_decisions() -> None:
    """The brief tells agents who the writer is, what to remember, and what they declined."""

    async def scenario() -> None:
        """Build a profile, memories, and decided proposals, then brief."""
        async with memory_session() as session:
            project_id = await _big_fish(session)
            session.add(WriterProfile(pen_name="J. A.", style_notes="Lean action, wry dialogue.", preferences={"avoid": ["flashback voice-over"]}))
            session.add(WriterMemory(kind="taboo", text="Never kill the dog.", pinned=True))
            other = Project(title="Another film")
            session.add(other)
            await session.flush()
            session.add(WriterMemory(kind="preference", text="Other project only.", project_id=other.id))
            for status in ("approved", "approved", "rejected"):
                session.add(AgentProposal(project_id=project_id, target_kind="block", target_id=1, operation={}, diff={}, before={}, base_version=1, status=status))
            await session.commit()
            brief = await writer_twin_brief(session, project_id)
            assert "J. A." in brief and "Lean action" in brief and "flashback voice-over" in brief
            assert "Never kill the dog." in brief and "Other project only." not in brief
            assert "2 approved, 1 rejected" in brief

    run_async(scenario())
