"""Render a canonical screenplay document to a portable best-effort PDF."""

from html import escape
from io import BytesIO

from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from draftpilot.core.screenplay.schema import BlockDoc, SceneDoc, ScreenplayDoc


def _text(value: str) -> str:
    """Escape screenplay text for ReportLab's paragraph markup."""
    return escape(value).replace("\n", "<br/>")


def _paragraph(block: BlockDoc, styles: dict[str, ParagraphStyle]) -> Paragraph:
    """Build one styled PDF paragraph from a semantic screenplay block."""
    style_name = block.element_type.value
    style = styles.get(style_name, styles["action"])
    text = _text(block.text)
    if block.element_type.value == "character":
        text = text.upper()
    return Paragraph(text or "&nbsp;", style)


def _scene_flow(scene: SceneDoc, styles: dict[str, ParagraphStyle]) -> list[object]:
    """Build the PDF flowable sequence for one scene."""
    flow: list[object] = [Paragraph(_text(scene.heading).upper(), styles["heading"]), Spacer(1, 0.12 * inch)]
    flow.extend(_paragraph(block, styles) for block in scene.blocks)
    flow.append(Spacer(1, 0.22 * inch))
    return flow


def render_pdf(doc: ScreenplayDoc) -> bytes:
    """Render screenplay semantics into a best-effort PDF byte string."""
    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        rightMargin=1.0 * inch,
        leftMargin=1.25 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title=doc.title_page.get("Title", "DraftPilot screenplay"),
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("screenplay-title", parent=base["Title"], alignment=TA_CENTER, spaceAfter=24),
        "heading": ParagraphStyle("screenplay-heading", parent=base["Normal"], fontName="Helvetica-Bold", alignment=TA_LEFT, spaceBefore=12),
        "action": ParagraphStyle("screenplay-action", parent=base["BodyText"], fontName="Helvetica", leading=14, spaceAfter=8),
        "character": ParagraphStyle("screenplay-character", parent=base["BodyText"], fontName="Helvetica-Bold", leftIndent=1.8 * inch, leading=13, spaceBefore=7),
        "dialogue": ParagraphStyle("screenplay-dialogue", parent=base["BodyText"], leftIndent=1.0 * inch, rightIndent=1.0 * inch, leading=14, spaceAfter=8),
        "parenthetical": ParagraphStyle("screenplay-parenthetical", parent=base["BodyText"], leftIndent=1.25 * inch, rightIndent=1.25 * inch, fontName="Helvetica-Oblique", leading=13, spaceAfter=3),
        "transition": ParagraphStyle("screenplay-transition", parent=base["BodyText"], fontName="Helvetica-Bold", alignment=TA_LEFT, spaceBefore=8, spaceAfter=8),
    }
    story: list[object] = []
    title = doc.title_page.get("Title")
    if title:
        story.extend([Spacer(1, 2.2 * inch), Paragraph(_text(title), styles["title"])])
        for key, value in doc.title_page.items():
            if key != "Title":
                story.append(Paragraph(f"{_text(key)}: {_text(value)}", base["Normal"]))
        story.append(PageBreak())
    for act_index, act in enumerate(doc.acts):
        if act.title:
            story.append(Paragraph(_text(act.title), styles["heading"]))
        for scene in act.scenes:
            story.extend(_scene_flow(scene, styles))
        if act_index < len(doc.acts) - 1:
            story.append(PageBreak())
    if not story:
        story.append(Paragraph("DraftPilot screenplay", styles["title"]))
    pdf.build(story)
    return buffer.getvalue()
