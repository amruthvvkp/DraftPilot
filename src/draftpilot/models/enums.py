"""Shared enumerations for screenplay structure and project metadata."""

from enum import Enum


class BlockType(str, Enum):
    """Enumerate the kinds of screenplay element a scene block can hold."""

    ACTION = "action"
    CHARACTER = "character"
    DIALOGUE = "dialogue"
    PARENTHETICAL = "parenthetical"
    TRANSITION = "transition"
    LYRIC = "lyric"
    NOTE = "note"
    SECTION = "section"
    SYNOPSIS = "synopsis"
    SHOT = "shot"
    PAGE_BREAK = "page_break"


class ReferenceKind(str, Enum):
    """Enumerate the categories of creative reference a project can cite."""

    FILM = "film"
    DIRECTOR = "director"
    SHORT = "short"
    ONLINE = "online"
    TV = "tv"
    ACTING = "acting"
    PLACE = "place"
    OTHER = "other"


class ScreeningType(str, Enum):
    """Enumerate the intended exhibition/aspect formats for a project."""

    IMAX_1_43 = "imax_1_43"
    FLAT_1_85 = "flat_1_85"
    CINEMASCOPE_2_39 = "cinemascope_2_39"
    WIDESCREEN_1_78 = "widescreen_1_78"
    ACADEMY_1_37 = "academy_1_37"
    OTHER = "other"
