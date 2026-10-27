"""Test id-stable scene restores, three-query loads, title pages, and authorship."""

from _async import run_async
from _db import memory_session
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.screenplay.hydrate import (
    apply_scene_doc,
    blocks_for_scene,
    load_screenplay_doc,
    save_screenplay_doc,
    scene_text,
    scene_to_doc,
)
from draftpilot.core.screenplay.schema import ActDoc, BlockDoc, SceneDoc, ScreenplayDoc
from draftpilot.crud import scene_revisions as revisions_crud
from draftpilot.models import (
    Act,
    Block,
    BlockType,
    DialogueTranslation,
    Project,
    Scene,
    Screenplay,
)


async def _scene(session: AsyncSession) -> Scene:
    """Persist one project, screenplay, act, and a three-block scene."""
    project = Project(title="Big Fish")
    session.add(project)
    await session.flush()
    screenplay = Screenplay(project_id=project.id or 0, title="Big Fish")
    session.add(screenplay)
    await session.flush()
    act = Act(screenplay_id=screenplay.id or 0, title="Act One")
    session.add(act)
    await session.flush()
    scene = Scene(act_id=act.id or 0, heading="INT. BLOOM HOUSE - NIGHT")
    session.add(scene)
    await session.flush()
    session.add_all(
        [
            Block(scene_id=scene.id or 0, position=0, element_type=BlockType.ACTION, text="Rain."),
            Block(scene_id=scene.id or 0, position=1, element_type=BlockType.CHARACTER, text="EDWARD"),
            Block(scene_id=scene.id or 0, position=2, element_type=BlockType.DIALOGUE, text="A fish."),
        ]
    )
    await session.commit()
    return scene


def test_restore_keeps_block_ids_and_linked_translations() -> None:
    """Restoring a revision updates blocks in place, so translations survive."""

    async def scenario() -> None:
        """Snapshot, edit, then restore the scene."""
        async with memory_session() as session:
            scene = await _scene(session)
            blocks = await blocks_for_scene(session, scene.id or 0)
            dialogue = blocks[2]
            session.add(DialogueTranslation(block_id=dialogue.id or 0, language="Hindi", text="एक मछली।"))
            await session.commit()
            revision = await revisions_crud.snapshot(session, scene, "before rewrite")
            assert revision.snapshot["blocks"][2]["id"] == dialogue.id
            dialogue.text = "A different fish."
            session.add(Block(scene_id=scene.id or 0, position=3, text="Thunder."))
            await session.commit()

            await revisions_crud.restore(session, scene, revision)

            restored = await blocks_for_scene(session, scene.id or 0)
            assert [block.id for block in restored] == [block.id for block in blocks]
            assert restored[2].text == "A fish."
            translations = (await session.exec(select(DialogueTranslation))).all()
            assert [item.text for item in translations] == ["एक मछली।"]

    run_async(scenario())


def test_legacy_snapshots_without_ids_restore_by_position() -> None:
    """Snapshots recorded before block ids reuse existing blocks by position."""

    async def scenario() -> None:
        """Apply an id-less document with one block fewer."""
        async with memory_session() as session:
            scene = await _scene(session)
            before = [block.id for block in await blocks_for_scene(session, scene.id or 0)]
            legacy = SceneDoc(heading="EXT. RIVER - DAY", blocks=[BlockDoc(text="Water."), BlockDoc(text="Mud.")])
            await apply_scene_doc(session, scene, legacy)
            after = await blocks_for_scene(session, scene.id or 0)
            assert [block.id for block in after] == before[:2]
            assert [block.text for block in after] == ["Water.", "Mud."]
            assert scene.heading == "EXT. RIVER - DAY"

    run_async(scenario())


def test_documents_round_trip_title_page_and_authorship() -> None:
    """Saving a document persists the title page and marks imported text by origin."""

    async def scenario() -> None:
        """Save then load a two-act document."""
        async with memory_session() as session:
            project = Project(title="Big Fish")
            session.add(project)
            await session.flush()
            screenplay = Screenplay(project_id=project.id or 0, title="Big Fish")
            session.add(screenplay)
            await session.commit()
            doc = ScreenplayDoc(
                title_page={"Title": "Big Fish", "Author": "John August"},
                acts=[
                    ActDoc(title="Act One", scenes=[SceneDoc(heading="INT. A", blocks=[BlockDoc(id=999, text="One.")])]),
                    ActDoc(title="Act Two", scenes=[SceneDoc(heading="INT. B", blocks=[BlockDoc(text="Two.")])]),
                ],
            )
            await save_screenplay_doc(session, screenplay.id or 0, doc)
            loaded = await load_screenplay_doc(session, screenplay.id or 0)
            assert loaded.title_page == {"Title": "Big Fish", "Author": "John August"}
            assert [act.title for act in loaded.acts] == ["Act One", "Act Two"]
            first = loaded.acts[0].scenes[0].blocks[0]
            assert first.text == "One." and first.origin == "import" and first.id != 999

    run_async(scenario())


def test_scene_text_covers_the_whole_scene() -> None:
    """The indexed scene text includes the heading and every block, not just the last edit."""

    async def scenario() -> None:
        """Build the RAG text for a persisted scene."""
        async with memory_session() as session:
            scene = await _scene(session)
            text = scene_text(scene.heading, await blocks_for_scene(session, scene.id or 0))
            assert text == "INT. BLOOM HOUSE - NIGHT\nRain.\nEDWARD\nA fish."
            assert (await scene_to_doc(session, scene)).blocks[0].origin == "human"

    run_async(scenario())
