"""Bridge between ``screenplay-tools`` ``Script`` objects and ``ScreenplayDoc``.

Both the Fountain and FDX adapters parse into / render from the same
``screenplay_tools.screenplay.Script`` intermediate, so the element-level mapping
lives here and is shared.
"""

from itertools import pairwise

from screenplay_tools import screenplay as st

from draftpilot.core.screenplay.schema import ActDoc, BlockDoc, SceneDoc, ScreenplayDoc
from draftpilot.models.enums import BlockType

# screenplay-tools ElementType name -> our BlockType (HEADING is handled as a
# scene boundary, not a block; BONEYARD collapses to a NOTE block).
_ST_TO_BLOCK: dict[str, BlockType] = {
    "ACTION": BlockType.ACTION,
    "CHARACTER": BlockType.CHARACTER,
    "DIALOGUE": BlockType.DIALOGUE,
    "PARENTHETICAL": BlockType.PARENTHETICAL,
    "TRANSITION": BlockType.TRANSITION,
    "LYRIC": BlockType.LYRIC,
    "NOTE": BlockType.NOTE,
    "BONEYARD": BlockType.NOTE,
    "SECTION": BlockType.SECTION,
    "SYNOPSIS": BlockType.SYNOPSIS,
    "PAGEBREAK": BlockType.PAGE_BREAK,
}


def _element_to_block(element: st.Element) -> BlockDoc:
    """Convert one ``screenplay-tools`` element into a ``BlockDoc``."""
    block_type = _ST_TO_BLOCK.get(element.type.name, BlockType.ACTION)
    if isinstance(element, st.Character):
        return BlockDoc(
            element_type=BlockType.CHARACTER,
            text=element.name,
            character_extension=element.extension,
            is_dual=element.is_dual_dialogue,
        )
    if isinstance(element, st.Section):
        return BlockDoc(
            element_type=BlockType.SECTION,
            text=element.text,
            marks={"level": element.level},
        )
    return BlockDoc(element_type=block_type, text=element.text)


_SPEECH = {BlockType.CHARACTER, BlockType.PARENTHETICAL, BlockType.DIALOGUE}


def _speeches(blocks: list[BlockDoc]) -> list[range]:
    """Split a scene's blocks into speeches: a cue and the dialogue under it."""
    found: list[range] = []
    start: int | None = None
    for index, block in enumerate(blocks):
        if block.element_type not in _SPEECH:
            if start is not None:
                found.append(range(start, index))
            start = None
        elif block.element_type is BlockType.CHARACTER or start is None:
            if start is not None:
                found.append(range(start, index))
            start = index
    if start is not None:
        found.append(range(start, len(blocks)))
    return found


def _link_dual_dialogue(blocks: list[BlockDoc]) -> None:
    """Group each ``^`` cue's speech with the speech before it (both get ``is_dual`` and a group)."""
    group = 0
    for previous, speech in pairwise(_speeches(blocks)):
        cue = blocks[speech.start]
        if (
            not cue.is_dual
            or cue.dual_group is not None
            or previous.stop != speech.start
        ):
            continue
        group += 1
        for index in [*previous, *speech]:
            blocks[index].is_dual = True
            blocks[index].dual_group = group


def _second_dual_cues(blocks: list[BlockDoc]) -> set[int]:
    """Return the indexes of cues that close a dual dialogue pair (they carry the ``^``)."""
    seen: set[int] = set()
    second: set[int] = set()
    for index, block in enumerate(blocks):
        if block.element_type is not BlockType.CHARACTER or not block.is_dual:
            continue
        # Without a group (older imports) only the second cue was ever marked dual.
        if block.dual_group is None or block.dual_group in seen:
            second.add(index)
        else:
            seen.add(block.dual_group)
    return second


def script_to_doc(script: st.Script) -> ScreenplayDoc:
    """Convert a ``screenplay-tools`` ``Script`` into a single-act ``ScreenplayDoc``."""
    title_page = {entry.key: entry.text for entry in script.titleEntries}
    scenes: list[SceneDoc] = []
    current: SceneDoc | None = None
    for element in script.elements:
        if element.type is st.ElementType.HEADING:
            current = SceneDoc(heading=element.text)
            scenes.append(current)
            continue
        if current is None:
            current = SceneDoc(heading="")
            scenes.append(current)
        current.blocks.append(_element_to_block(element))
    for scene in scenes:
        _link_dual_dialogue(scene.blocks)
    return ScreenplayDoc(title_page=title_page, acts=[ActDoc(scenes=scenes)])


def _block_to_element(block: BlockDoc, dual: bool = False) -> st.Element:
    """Convert one ``BlockDoc`` back into a ``screenplay-tools`` element."""
    match block.element_type:
        case BlockType.CHARACTER:
            return st.Character(
                block.text, extension=block.character_extension, dual=dual
            )
        case BlockType.SECTION:
            level = int((block.marks or {}).get("level", 1))
            return st.Section(level, block.text)
        case BlockType.PAGE_BREAK:
            return st.PageBreak()
        case BlockType.PARENTHETICAL:
            return st.Parenthetical(block.text)
        case BlockType.DIALOGUE:
            return st.Dialogue(block.text)
        case BlockType.TRANSITION:
            return st.Transition(block.text)
        case BlockType.LYRIC:
            return st.Lyric(block.text)
        case BlockType.NOTE:
            return st.Note(block.text)
        case BlockType.SYNOPSIS:
            return st.Synopsis(block.text)
        case _:
            # ACTION and SHOT (no Fountain/FDX equivalent) render as action.
            return st.Action(block.text)


def doc_to_script(doc: ScreenplayDoc) -> st.Script:
    """Convert a ``ScreenplayDoc`` into a ``screenplay-tools`` ``Script``.

    Act boundaries are a DraftPilot-side organizational layer and are not
    represented in the flat Fountain/FDX element stream; scenes are emitted in
    order across all acts.
    """
    script = st.Script()
    for key, value in doc.title_page.items():
        script.add_element(st.TitleEntry(key, value))
    for act in doc.acts:
        for scene in act.scenes:
            if scene.heading:
                script.add_element(st.SceneHeading(scene.heading))
            second = _second_dual_cues(scene.blocks)
            for index, block in enumerate(scene.blocks):
                script.add_element(_block_to_element(block, dual=index in second))
    return script
