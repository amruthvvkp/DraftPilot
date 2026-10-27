"""Render canonical screenplay documents as safe, print-ready HTML."""

from html import escape

from draftpilot.core.screenplay.schema import ActDoc, BlockDoc, SceneDoc, ScreenplayDoc


def _inline_text(value: str) -> str:
    """Escape screenplay text while retaining intentional line breaks."""
    return escape(value).replace("\n", "<br>")


def _block_markup(block: BlockDoc) -> str:
    """Render one semantic block with a stable CSS class."""
    classes = ["screenplay-block", block.element_type.value]
    if block.is_dual:
        classes.append("dual-dialogue")
    text = _inline_text(block.text)
    if block.element_type.value == "character":
        text = text.upper()
    return f'<p class="{" ".join(classes)}">{text or "&nbsp;"}</p>'


def _scene_markup(scene: SceneDoc) -> str:
    """Render one scene heading and its ordered blocks."""
    blocks = "".join(_block_markup(block) for block in scene.blocks)
    return f'<section class="screenplay-scene"><h2 class="scene-heading">{_inline_text(scene.heading).upper()}</h2>{blocks}</section>'


def _act_markup(act: ActDoc) -> str:
    """Render one act and its scenes."""
    title = f'<h1 class="act-title">{_inline_text(act.title)}</h1>' if act.title else ""
    scenes = "".join(_scene_markup(scene) for scene in act.scenes)
    return f'<section class="screenplay-act">{title}{scenes}</section>'


def render_html(doc: ScreenplayDoc) -> str:
    """Render a self-contained screenplay HTML document without executable content."""
    title = escape(doc.title_page.get("Title", "DraftPilot screenplay"))
    metadata = "".join(
        f'<dt>{escape(key)}</dt><dd>{_inline_text(value)}</dd>'
        for key, value in doc.title_page.items()
        if key != "Title"
    )
    title_page = f'<header class="title-page"><h1>{title}</h1><dl>{metadata}</dl></header>' if doc.title_page else ""
    acts = "".join(_act_markup(act) for act in doc.acts)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ margin: 0; background: #e8e5df; color: #171614; font: 12pt/1.45 Georgia, serif; }}
.screenplay {{ max-width: 8.5in; margin: 2rem auto; padding: 1in 1.25in; background: #fff; box-sizing: border-box; }}
.title-page {{ min-height: 6in; display: grid; place-content: center; text-align: center; page-break-after: always; }}
.title-page h1 {{ font-size: 2rem; }} .title-page dl {{ display: grid; grid-template-columns: auto auto; gap: .25rem 1rem; text-align: left; }}
.act-title {{ text-align: center; font-size: 1rem; text-transform: uppercase; }}
.screenplay-scene {{ margin: 1.2rem 0 2rem; break-inside: avoid; }}
.scene-heading {{ font: 700 1rem/1.3 Arial, sans-serif; text-transform: uppercase; margin: 0 0 1rem; }}
.screenplay-block {{ margin: .45rem 0; }} .character {{ margin: 1rem 0 0 2.1in; font-weight: 700; }}
.dialogue {{ margin: 0 1.1in; }} .parenthetical {{ margin: 0 1.35in; font-style: italic; }}
.transition {{ text-align: right; font-weight: 700; }} .dual-dialogue {{ border-left: 2px solid #d69b55; padding-left: .5rem; }}
@media print {{ body {{ background: #fff; }} .screenplay {{ margin: 0; box-shadow: none; }} }}
</style>
</head>
<body><main class="screenplay">{title_page}{acts}</main></body>
</html>'''
