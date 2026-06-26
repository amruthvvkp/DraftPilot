"""Final Draft (FDX) ⇄ ``ScreenplayDoc`` adapter built on ``screenplay-tools``."""

from screenplay_tools.fdx.parser import Parser
from screenplay_tools.fdx.writer import Writer

from draftpilot.core.screenplay.adapters._bridge import doc_to_script, script_to_doc
from draftpilot.core.screenplay.schema import ScreenplayDoc


def parse_fdx(xml: str) -> ScreenplayDoc:
    """Parse Final Draft FDX XML into a ``ScreenplayDoc``."""
    return script_to_doc(Parser().parse(xml))


def render_fdx(doc: ScreenplayDoc) -> str:
    """Render a ``ScreenplayDoc`` to Final Draft FDX XML."""
    return Writer().write(doc_to_script(doc))
