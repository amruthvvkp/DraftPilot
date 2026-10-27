"""Python Playwright journeys for the single-document script editor (Settings → Editor: Document).

The API is an in-memory fake of the workspace, the batched scene content endpoint and agent
proposals, so the journeys exercise the editor's saves, conflicts and inline proposals without a
database.
"""

import json
import re
from typing import Any

from playwright.sync_api import BrowserContext, Locator, Page, Route, expect

DOCUMENT_MODE = "localStorage.setItem('draftpilot:editor', 'document')"
PROJECT = {
    "id": 9001, "title": "The Lantern House", "logline": "A family returns to a house that remembers.", "description": "",
    "genres": ["Drama"], "languages": ["English", "Hindi"], "primary_language": "English", "project_instruction": "", "version": 1, "artwork_url": None,
}


class FakeStudio:
    """Serve one project's workspace and apply content writes and proposals to it, like the server."""

    def __init__(self, scenes: list[tuple[int, str, list[tuple[str, str]]]], proposals: list[dict[str, Any]] | None = None, beats: list[dict[str, Any]] | None = None) -> None:
        """Build the fixture from (scene id, heading, [(element type, text)]) tuples."""
        self.next_id = 100
        self.scenes = [{"id": scene_id, "act_id": 4, "heading": heading, "position": index, "body": "", "version": 2, "scene_instruction": ""} for index, (scene_id, heading, _) in enumerate(scenes)]
        self.blocks: dict[int, list[dict[str, Any]]] = {scene_id: [self._block(scene_id, kind, text) for kind, text in items] for scene_id, _, items in scenes}
        self.proposals = proposals or []
        self.beats = beats or []
        self.writes: list[dict[str, Any]] = []

    def _block(self, scene_id: int, kind: str, text: str, origin: str = "human") -> dict[str, Any]:
        """Create a block row with the next id."""
        self.next_id += 1
        return {"id": self.next_id, "scene_id": scene_id, "position": 0, "element_type": kind, "text": text, "character_extension": None,
                "is_dual": False, "dual_group": None, "translation": None, "translation_lang": None, "origin": origin}

    def scene(self, scene_id: int) -> dict[str, Any]:
        """Return a scene row."""
        return next(scene for scene in self.scenes if scene["id"] == scene_id)

    def texts(self, scene_id: int) -> list[tuple[str, str]]:
        """Return a scene's blocks as (element type, text) pairs."""
        return [(block["element_type"], block["text"]) for block in self.blocks[scene_id]]

    def workspace(self) -> dict[str, Any]:
        """Return the workspace payload."""
        for rows in self.blocks.values():
            for position, row in enumerate(rows):
                row["position"] = position
        return {"project": PROJECT, "screenplay": {"id": 12, "project_id": 9001, "title": "The Lantern House", "format": "feature", "status": "draft", "title_page": {"Title": "The Lantern House", "Credit": "Written by"}},
                "acts": [{"id": 4, "screenplay_id": 12, "title": "Act One", "position": 0}], "scenes": self.scenes, "blocks": {str(key): value for key, value in self.blocks.items()}}

    def write_content(self, scene_id: int, version: int, payload: dict[str, Any]) -> tuple[int, Any]:
        """Apply a batched scene write: keep posted ids, create the rest, bump the version once."""
        scene = self.scene(scene_id)
        if version != scene["version"]:
            return 409, {"detail": "Version mismatch"}
        self.writes.append({"scene_id": scene_id, **payload})
        existing = {block["id"]: block for block in self.blocks[scene_id]}
        rows, created = [], []
        for item in payload["blocks"]:
            if item.get("id") in existing:
                row = existing[item["id"]]
                if row["text"] != item["text"] or row["element_type"] != item["element_type"]:
                    row["origin"] = "human"
                row.update({key: item[key] for key in ("element_type", "text", "is_dual", "dual_group") if key in item})
            else:
                row = self._block(scene_id, item["element_type"], item["text"])
                created.append(row["id"])
            rows.append(row)
        self.blocks[scene_id] = rows
        if payload.get("heading") is not None:
            scene["heading"] = payload["heading"]
        scene["version"] += 1
        return 200, {"scene_id": scene_id, "version": scene["version"], "block_ids": [row["id"] for row in rows], "created_ids": created}

    def respond(self, route: Route) -> None:
        """Route every API call of the journey."""
        request = route.request
        path = request.url.split("/api/v1", 1)[-1].split("?", 1)[0]
        payload = request.post_data_json if request.post_data else {}
        code, result = 200, []
        if path == "/projects":
            result = [PROJECT]
        elif path.endswith("/workspace"):
            result = self.workspace()
        elif match := re.fullmatch(r"/projects/9001/scenes/(\d+)/content", path):
            code, result = self.write_content(int(match.group(1)), int(request.headers.get("if-match", "0")), payload)
        elif path.endswith("/agent-proposals"):
            result = self.proposals
        elif match := re.fullmatch(r"/projects/9001/agent-proposals/(\d+)/(approve|reject|rollback)", path):
            result = self.decide(int(match.group(1)), match.group(2))
        elif path.endswith("/beats"):
            result = self.beats
        elif path == "/writer/profile":
            result = {"name": "", "pen_name": "", "bio": "", "default_format": "feature", "default_language": "English", "style_notes": "", "preferences": {}}
        elif path.endswith("/agents/roles"):
            result = [{"key": "story_architect", "label": "Story architect", "description": "Shape the story.", "default_permission": "chat_only"}]
        elif path.endswith("/events"):
            route.fulfill(status=200, content_type="text/event-stream", body="")
            return
        route.fulfill(status=code, content_type="application/json", body=json.dumps(result))

    def decide(self, proposal_id: int, action: str) -> dict[str, Any]:
        """Approve, reject or roll back a block proposal."""
        proposal = next(item for item in self.proposals if item["id"] == proposal_id)
        block = next(row for rows in self.blocks.values() for row in rows if row["id"] == proposal["target_id"])
        scene = self.scene(block["scene_id"])
        if action == "approve":
            proposal["before"] = {"text": block["text"], "origin": block["origin"]}
            block.update(proposal["operation"], origin=f"proposal:{proposal_id}")
            proposal["status"] = "approved"
            scene["version"] += 1
        elif action == "rollback":
            block.update(proposal["before"])
            proposal["status"] = "rolled_back"
            scene["version"] += 1
        else:
            proposal["status"] = "rejected"
        return proposal


def _open(context: BrowserContext, page: Page, studio: FakeStudio) -> None:
    """Route the context to the fake, switch to the Document editor and open the project."""
    context.add_init_script(DOCUMENT_MODE)
    context.route("**/api/v1/**", studio.respond)
    page.goto("/projects/9001")
    expect(page.get_by_role("textbox", name="Screenplay")).to_be_visible()


def _caret_at_end(box: Locator) -> None:
    """Click into an element and put the caret at its end (End doesn't move the caret on macOS)."""
    box.click()
    box.evaluate("el => { const range = document.createRange(); range.selectNodeContents(el); range.collapse(false); const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range) }")


def _saved(page: Page) -> None:
    """Wait for the editor to report every change saved."""
    expect(page.get_by_role("status", name="Save status")).to_have_text("All changes saved", timeout=10_000)


def test_settings_switches_the_script_editor(page: Page) -> None:
    """Settings → Editor picks Classic or Document; Classic stays the default."""
    studio = FakeStudio([(7, "INT. LANTERN HOUSE - NIGHT", [("action", "The house breathes.")])])
    page.route("**/api/v1/**", studio.respond)
    page.goto("/settings")
    editor = page.get_by_role("radiogroup", name="Script editor")
    expect(editor.get_by_role("radio", name="Classic")).to_have_attribute("aria-checked", "true")
    editor.get_by_role("radio", name="Document").click()
    expect(editor.get_by_role("radio", name="Document")).to_have_attribute("aria-checked", "true")
    page.goto("/projects/9001")
    expect(page.get_by_role("textbox", name="Action 1")).to_have_text("The house breathes.")
    expect(page.get_by_label("Edit action")).to_have_count(0)


def test_document_scene_written_with_the_keyboard_only(page: Page) -> None:
    """Enter and Tab pick the next element, ⌘B bolds, and the scene saves as one batched write."""
    studio = FakeStudio([(7, "INT. LANTERN HOUSE - NIGHT", [])])
    _open(page.context, page, studio)
    heading = page.get_by_role("textbox", name="Scene heading 1")
    expect(heading).to_have_text("INT. LANTERN HOUSE - NIGHT")
    expect(page.get_by_role("region", name="Title page")).to_contain_text("The Lantern House")
    heading.click()
    keys = page.keyboard
    keys.press("Enter")  # Enter anywhere in a heading moves into the scene
    keys.type("The house breathes in the dark.")
    keys.press("Enter")
    keys.press("Tab")
    keys.type("mira")
    keys.press("Enter")
    keys.type("We should go.")
    keys.press("Enter")
    keys.press("Enter")
    keys.type("EDWARD")
    keys.press("Enter")
    keys.press("Tab")
    keys.type("(softly)")
    keys.press("Enter")
    keys.type("Not yet.")
    for _ in range(4):
        keys.press("Shift+ArrowLeft")
    expect(page.get_by_role("toolbar", name="Screenplay formatting toolbar")).to_be_visible()
    keys.press("ControlOrMeta+b")
    _saved(page)
    assert studio.texts(7) == [
        ("action", "The house breathes in the dark."), ("character", "MIRA"), ("dialogue", "We should go."),
        ("character", "EDWARD"), ("parenthetical", "(softly)"), ("dialogue", "Not **yet.**"),
    ]
    assert len(studio.writes) <= 3, "saves are debounced and batched per scene"
    expect(page.get_by_role("textbox", name="Dialogue 2")).to_have_text("Not yet.")
    expect(page.get_by_role("textbox", name="Dialogue 2").locator("strong")).to_have_text("yet.")
    # Undo stays local to the editor and saves again.
    keys.press("ControlOrMeta+z")
    _saved(page)
    assert studio.texts(7)[-1] == ("dialogue", "Not yet.")


def test_document_workspace_journey(page: Page) -> None:
    """The classic workspace journey in the Document editor: outline inline, formatting, types, navigator."""
    beats = [
        {"id": 50, "project_id": 9001, "version": 1, "act_id": 4, "position": 0, "title": "Arrival", "summary": "Mira returns home.", "beat_type": "beat", "status": "planned", "scene_ids": [7], "character_ids": [], "source": "writer"},
        {"id": 51, "project_id": 9001, "version": 1, "act_id": 4, "position": 1, "title": "The cellar door", "summary": "", "beat_type": "beat", "status": "planned", "scene_ids": [], "character_ids": [], "source": "writer"},
    ]
    studio = FakeStudio([
        (7, "INT. LANTERN HOUSE - NIGHT", [("action", "The house breathes in the **dark**."), ("character", "MIRA"), ("dialogue", "We *should* go.")]),
        (8, "EXT. GARDEN - DAY", [("action", "Rain on the roses.")]),
    ], beats=beats)
    _open(page.context, page, studio)
    expect(page.get_by_role("group", name="Beat: Arrival")).to_be_visible()
    expect(page.get_by_role("group", name="Beat: The cellar door").get_by_role("button", name="Create scene from beat")).to_be_visible()
    page.get_by_role("switch", name="Outline").click()
    expect(page.get_by_role("group", name="Beat: Arrival")).to_be_hidden()
    page.get_by_role("switch", name="Outline").click()

    action = page.get_by_role("textbox", name="Action 1")
    expect(action.locator("strong")).to_have_text("dark")
    _caret_at_end(action)
    page.keyboard.type(" Still.")
    page.get_by_role("combobox", name="Current element type").select_option("shot")
    _saved(page)
    assert studio.texts(7)[0] == ("shot", "The house breathes in the **dark**. Still.")
    assert studio.texts(7)[1:] == [("character", "MIRA"), ("dialogue", "We *should* go.")], "untouched blocks keep their exact text"
    assert len(studio.writes) == 1 and 8 not in [write.get("scene_id") for write in studio.writes]

    # The navigator jumps to a scene; the rail and navigator collapse.
    page.get_by_role("button", name=re.compile("EXT. GARDEN - DAY")).click()
    expect(page.get_by_role("textbox", name="Screenplay")).to_be_focused()
    page.keyboard.type(" AT DUSK")
    _saved(page)
    assert studio.scene(8)["heading"] == "EXT. GARDEN - DAY AT DUSK"
    page.get_by_role("button", name="Hide navigator").click()
    page.get_by_role("button", name="Hide context rail").click()
    expect(page.get_by_role("button", name="Show navigator")).to_be_visible()
    expect(page.get_by_role("textbox", name="Action 1")).to_have_text("Rain on the roses.")


def test_document_inline_proposal_accept_and_roll_back(page: Page) -> None:
    """A pending agent proposal sits under its block; nothing changes until the writer accepts."""
    proposal = {"id": 80, "project_id": 9001, "run_id": None, "target_kind": "block", "target_id": 0, "operation": {"text": "Rain hammers the roses."},
                "diff": {"summary": "Sharper verb"}, "before": {}, "base_version": 2, "status": "proposed"}
    studio = FakeStudio([(7, "EXT. GARDEN - DAY", [("action", "Rain on the roses.")])], proposals=[proposal])
    proposal["target_id"] = studio.blocks[7][0]["id"]
    _open(page.context, page, studio)
    card = page.get_by_role("group", name="Proposal 80 from Agent")
    expect(card).to_contain_text("Sharper verb")
    expect(card.locator("del")).to_have_text("on")
    expect(card.locator("ins")).to_have_text("hammers")
    expect(page.get_by_role("textbox", name="Action 1")).to_have_text("Rain on the roses.")
    card.get_by_role("button", name="Accept proposal 80").click()
    expect(page.get_by_role("textbox", name="Action 1")).to_have_text("Rain hammers the roses.")
    expect(card).to_have_count(0)
    page.get_by_role("group", name="Accepted proposal 80").get_by_role("button", name="Roll back proposal 80").click()
    expect(page.get_by_role("textbox", name="Action 1")).to_have_text("Rain on the roses.")
    assert proposal["status"] == "rolled_back"
    assert not studio.writes, "accepting and rolling back go through the proposal endpoints, not editor saves"


def test_document_conflict_from_a_second_tab(page: Page) -> None:
    """A stale save shows Keep mine / Load theirs; both resolve it."""
    studio = FakeStudio([(7, "INT. LANTERN HOUSE - NIGHT", [("action", "One.")])])
    _open(page.context, page, studio)
    second = page.context.new_page()
    second.goto("/projects/9001")
    expect(second.get_by_role("textbox", name="Action 1")).to_have_text("One.")

    _caret_at_end(page.get_by_role("textbox", name="Action 1"))
    page.keyboard.type(" First tab.")
    _saved(page)

    _caret_at_end(second.get_by_role("textbox", name="Action 1"))
    second.keyboard.type(" Second tab.")
    bar = second.get_by_role("alert").filter(has_text="saved elsewhere")
    expect(bar).to_be_visible(timeout=10_000)
    bar.get_by_role("button", name="Load theirs").click()
    expect(second.get_by_role("textbox", name="Action 1")).to_have_text("One. First tab.")
    expect(bar).to_have_count(0)

    # The first tab is now behind: its next save conflicts, and Keep mine writes over the newer version.
    _caret_at_end(second.get_by_role("textbox", name="Action 1"))
    second.keyboard.type(" Again.")
    _saved(second)
    page.keyboard.type(" Mine wins.")
    bar = page.get_by_role("alert").filter(has_text="saved elsewhere")
    expect(bar).to_be_visible(timeout=10_000)
    bar.get_by_role("button", name="Keep mine").click()
    _saved(page)
    assert studio.texts(7) == [("action", "One. First tab. Mine wins.")]
