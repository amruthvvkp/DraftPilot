"""Best-effort text recovery from screenplay PDF files."""

import re
from io import BytesIO

from pypdf import PdfReader

from draftpilot.core.screenplay.schema import ActDoc, BlockDoc, SceneDoc, ScreenplayDoc
from draftpilot.models.enums import BlockType

MAX_PDF_PAGES = 500
MAX_EXTRACTED_CHARACTERS = 2_000_000
_HEADING = re.compile(r"^(INT\.?|EXT\.?|I/E\.?|INT\./EXT\.?)\b", re.IGNORECASE)


def _is_character_line(line: str) -> bool:
    """Return whether a short line resembles a screenplay character cue."""
    compact = line.strip()
    return (
        2 <= len(compact) <= 60
        and compact == compact.upper()
        and any(char.isalpha() for char in compact)
        and not compact.endswith((".", ",", ":", ";", "!", "?"))
    )


def _blocks(lines: list[str]) -> list[BlockDoc]:
    """Infer conservative semantic blocks from extracted PDF lines."""
    blocks: list[BlockDoc] = []
    dialogue = False
    for line in lines:
        text = line.strip()
        if not text:
            dialogue = False
            continue
        if _is_character_line(text):
            blocks.append(BlockDoc(element_type=BlockType.CHARACTER, text=text))
            dialogue = True
        elif dialogue:
            blocks.append(BlockDoc(element_type=BlockType.DIALOGUE, text=text))
        else:
            blocks.append(BlockDoc(element_type=BlockType.ACTION, text=text))
    return blocks


def parse_pdf(data: bytes) -> ScreenplayDoc:
    """Recover a screenplay document from bounded PDF text content."""
    if not data or len(data) > 20 * 1024 * 1024:
        raise ValueError("PDF is empty or exceeds the 20 MiB import limit")
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError("PDF exceeds the page limit")
        pages = [page.extract_text() or "" for page in reader.pages]
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Malformed or unreadable PDF") from exc
    text = "\n".join(pages)
    if len(text) > MAX_EXTRACTED_CHARACTERS:
        raise ValueError("Extracted PDF text exceeds the import limit")
    lines = [line.strip() for line in text.splitlines()]
    scenes: list[SceneDoc] = []
    current_heading = "IMPORTED PDF"
    current_lines: list[str] = []
    for line in lines:
        if _HEADING.match(line):
            if current_lines:
                scenes.append(SceneDoc(heading=current_heading, blocks=_blocks(current_lines)))
            current_heading = line
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines or not scenes:
        scenes.append(SceneDoc(heading=current_heading, blocks=_blocks(current_lines)))
    return ScreenplayDoc(acts=[ActDoc(title="Imported PDF", scenes=scenes)])
