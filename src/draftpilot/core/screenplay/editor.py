"""Typed screenplay authoring helpers for suggestions and keyboard transitions."""

from collections.abc import Sequence

from draftpilot.models.enums import BlockType

ELEMENT_ORDER: tuple[BlockType, ...] = (
    BlockType.ACTION,
    BlockType.CHARACTER,
    BlockType.PARENTHETICAL,
    BlockType.DIALOGUE,
    BlockType.TRANSITION,
)


def autocomplete_elements(prefix: str, limit: int = 8) -> list[BlockType]:
    """Return screenplay element types matching a typed prefix."""
    normalized = prefix.casefold().strip()
    matches = [element for element in ELEMENT_ORDER if element.value.startswith(normalized)]
    return matches[: max(0, limit)]


def autocomplete_characters(prefix: str, characters: Sequence[str], limit: int = 8) -> list[str]:
    """Return known character names matching a typed prefix."""
    normalized = prefix.casefold().strip()
    unique = dict.fromkeys(character.strip() for character in characters if character.strip())
    matches = [name for name in unique if name.casefold().startswith(normalized)]
    return matches[: max(0, limit)]


def next_element(current: BlockType) -> BlockType:
    """Return the next valid screenplay element for Tab navigation."""
    try:
        return ELEMENT_ORDER[(ELEMENT_ORDER.index(current) + 1) % len(ELEMENT_ORDER)]
    except ValueError:
        return BlockType.ACTION


def dual_dialogue_group(left_group: int | None, right_group: int | None) -> int:
    """Return a stable positive group identifier for paired dialogue."""
    return max(left_group or 0, right_group or 0, 0) + 1
