"""Fountain ⇄ ``ScreenplayDoc`` adapter built on ``screenplay-tools``."""

from screenplay_tools.fountain.parser import Parser
from screenplay_tools.fountain.writer import Writer

from draftpilot.core.screenplay.adapters._bridge import doc_to_script, script_to_doc
from draftpilot.core.screenplay.schema import ScreenplayDoc


def parse_fountain(text: str) -> ScreenplayDoc:
    """Parse Fountain source text into a ``ScreenplayDoc``."""
    parser = Parser()
    parser.add_text(text)
    parser.finalize()
    return script_to_doc(parser.script)


def render_fountain(doc: ScreenplayDoc) -> str:
    """Render a ``ScreenplayDoc`` to Fountain source text."""
    return Writer().write(doc_to_script(doc))
