"""Final Draft (FDX) ⇄ ``ScreenplayDoc`` adapter built on ``screenplay-tools``."""

import re

from screenplay_tools.fdx.parser import Parser
from screenplay_tools.fdx.writer import Writer

from draftpilot.core.screenplay.adapters._bridge import doc_to_script, script_to_doc
from draftpilot.core.screenplay.schema import ScreenplayDoc

_UNSAFE_XML_DECLARATION = re.compile(
    r"<!\s*(?:DOCTYPE|ENTITY)\b|\b(?:SYSTEM|PUBLIC)\s+(?:['\"]|\[)",
    re.IGNORECASE,
)


def _validate_fdx_xml(xml: str) -> None:
    """Reject DTD and external entity declarations before XML parsing."""
    if _UNSAFE_XML_DECLARATION.search(xml):
        raise ValueError("FDX imports cannot contain DTD or entity declarations")


def parse_fdx(xml: str) -> ScreenplayDoc:
    """Parse Final Draft FDX XML into a ``ScreenplayDoc``."""
    _validate_fdx_xml(xml)
    return script_to_doc(Parser().parse(xml))


def render_fdx(doc: ScreenplayDoc) -> str:
    """Render a ``ScreenplayDoc`` to Final Draft FDX XML."""
    return Writer().write(doc_to_script(doc))
