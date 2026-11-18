"""Python Playwright journey for the Journey map (mocked API): lanes, merge, reorder proposals, chronology edits."""

import json
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Page, Route, expect


def _character(character_id: int, name: str, position: int) -> dict[str, Any]:
    """Build a typed Character row."""
    return {
        "id": character_id, "project_id": 3, "version": 1, "position": position, "name": name, "role": "", "summary": "", "bio": "",
        "want": "", "need": "", "motive": "", "objective": "", "flaw": "", "arc_summary": "", "voice": "", "notes": "", "aliases": [],
        "tags": [], "cue": None, "dialogue_lines": 0, "scene_ids": [], "source": "writer", "writer_edited": False,
    }


def _event(event_id: int, character_id: int, title: str, **fields: object) -> dict[str, Any]:
    """Build a typed CharacterTimelineEvent row."""
    row: dict[str, Any] = {
        "id": event_id, "project_id": 3, "version": 1, "character_id": character_id, "position": event_id, "story_time": "", "title": title,
        "description": "", "objective": "", "emotional_state": "", "motivation": "", "history": "", "intensity": 0, "chrono_index": None,
        "scene_id": None, "beat_id": None, "moment_id": None,
    }
    row.update(fields)
    return row


class JourneyApi:
    """An in-memory project 3 with two acts, three scenes, two characters and their cards."""

    def __init__(self) -> None:
        """Seed the fixture."""
        self.acts = [{"id": 4, "screenplay_id": 12, "title": "Act One", "position": 0}, {"id": 5, "screenplay_id": 12, "title": "Act Two", "position": 1}]
        self.scenes = [
            {"id": 70, "act_id": 4, "heading": "INT. HOSPITAL - NIGHT", "position": 0, "body": "", "version": 1, "scene_instruction": ""},
            {"id": 71, "act_id": 4, "heading": "EXT. RIVER - DAY", "position": 1, "body": "", "version": 1, "scene_instruction": ""},
            {"id": 72, "act_id": 5, "heading": "INT. FUNERAL HOME - DAY", "position": 0, "body": "", "version": 1, "scene_instruction": ""},
        ]
        self.characters = [_character(1, "Will", 0), _character(2, "Edward", 1)]
        self.events = [
            _event(10, 1, "Flies home", scene_id=70, chrono_index=10, story_time="1998", objective="Make peace", intensity=-2),
            _event(11, 2, "Tells the witch story", scene_id=70, chrono_index=1, story_time="1950s", intensity=3),
            _event(12, 2, "Catches the fish", scene_id=71, chrono_index=2, story_time="1960s", intensity=4),
            _event(13, 1, "Says goodbye", scene_id=72, chrono_index=12, intensity=-5),
            _event(14, 1, "An untold idea"),
        ]
        self.moments: list[dict[str, Any]] = []
        self.variants: list[dict[str, Any]] = []
        self.proposals: list[dict[str, Any]] = []
        self.calls: list[tuple[str, str, str | None, Any]] = []

    def order(self) -> list[int]:
        """Return the script order (acts, then scenes)."""
        act_rank = {act["id"]: act["position"] for act in self.acts}
        return [scene["id"] for scene in sorted(self.scenes, key=lambda scene: (act_rank[scene["act_id"]], scene["position"]))]

    def _versioned(self, route: Route, rows: list[dict[str, Any]], row_id: int, payload: dict[str, Any]) -> object:
        """Apply a PATCH with If-Match, answering 409 on a stale version."""
        row = next(item for item in rows if item["id"] == row_id)
        if route.request.headers.get("if-match") != str(row["version"]):
            return None
        row.update(payload, version=row["version"] + 1)
        return row

    def respond(self, route: Route) -> None:
        """Serve the journey fixture and apply its writes."""
        request = route.request
        path = request.url.split("/api/v1/projects/3", 1)[-1].split("?", 1)[0]
        payload = request.post_data_json if request.post_data else {}
        self.calls.append((request.method, path, request.headers.get("if-match"), payload))
        result: object = []
        code = 200
        proposals = "/screenplays/12/timeline/proposals"
        if path == "/workspace":
            result = {
                "project": {"id": 3, "title": "Big Fish", "logline": None, "description": None, "genres": [], "languages": ["English"], "primary_language": "English", "project_instruction": "", "version": 1, "artwork_url": None},
                "screenplay": {"id": 12, "project_id": 3, "title": "Big Fish", "format": "feature", "status": "draft"},
                "acts": self.acts, "scenes": self.scenes, "blocks": {},
            }
        elif path == "/characters":
            result = self.characters
        elif path.startswith("/characters/") and request.method == "PATCH":
            result = self._versioned(route, self.characters, int(path.rsplit("/", 1)[-1]), payload)
        elif path == "/timeline-events" and request.method == "POST":
            result, code = _event(100 + len(self.events), payload["character_id"], payload["title"], chrono_index=payload.get("chrono_index")), 201
            self.events.append(result)  # type: ignore[arg-type]
        elif path == "/timeline-events":
            result = self.events
        elif path.startswith("/timeline-events/") and request.method == "PATCH":
            result = self._versioned(route, self.events, int(path.rsplit("/", 1)[-1]), payload)
        elif path == "/moments" and request.method == "POST":
            result = {"id": 50 + len(self.moments), "project_id": 3, "version": 1, "summary": "", "chrono_index": None, "story_time": "", "scene_id": None, "beat_id": None, **payload}
            self.moments.append(result)
            code = 201
        elif path == "/moments":
            result = self.moments
        elif path == "/narrative-variants" and request.method == "POST":
            result, code = {"id": 80 + len(self.variants), "project_id": 3, "version": 1, **payload}, 201
            self.variants.append(result)  # type: ignore[arg-type]
        elif path == "/narrative-variants":
            result = self.variants
        elif path == proposals and request.method == "POST":
            result = {"id": len(self.proposals) + 1, "project_id": 3, "screenplay_id": 12, "status": "proposed", "original_scene_ids": self.order(), "proposed_scene_ids": payload["scene_ids"], "timings": [], "total_runtime_seconds": 180}
            self.proposals.append(result)
        elif path == proposals:
            result = self.proposals
        elif path.startswith(proposals + "/"):
            proposal_id, action = path[len(proposals) + 1:].split("/")
            proposal = next(item for item in self.proposals if item["id"] == int(proposal_id))
            proposal["status"] = {"approve": "approved", "reject": "rejected", "rollback": "rolled_back"}[action]
            ids = proposal["proposed_scene_ids"] if action == "approve" else proposal["original_scene_ids"]
            if action != "reject":
                for scene in self.scenes:
                    scene["position"] = ids.index(scene["id"])
            result = proposal
        elif path == "/storyline":
            result = {"project_id": 3, "version": 1, "title": "Big Fish", "logline": None, "premise": None, "synopsis": None, "theme": None, "tone": None, "description": None, "story_outline": None}
        elif path == "/events":
            route.fulfill(status=204, body="")
            return
        if result is None:
            route.fulfill(status=409, content_type="application/json", body=json.dumps({"detail": "This changed"}))
            return
        route.fulfill(status=code, content_type="application/json", body=json.dumps(result))


def _until(page: Page, condition: Callable[[], bool], timeout_ms: int = 5000) -> None:
    """Wait until the fixture reaches a state (the browser writes asynchronously)."""
    for _ in range(timeout_ms // 100):
        if condition():
            return
        page.wait_for_timeout(100)
    assert condition()


def _open(page: Page) -> JourneyApi:
    """Mock the API and open the journey map."""
    api = JourneyApi()
    page.set_viewport_size({"width": 1600, "height": 1000})
    page.route("**/api/v1/projects/3/**", api.respond)
    page.goto("/projects/3/journey")
    expect(page.get_by_role("region", name="Journey map")).to_be_visible()
    return api


def test_journey_lanes_merge_and_chronology(page: Page) -> None:
    """Cards sit in character lanes; two cards merge into a shared moment only on the writer's click; chronology edits are versioned."""
    api = _open(page)
    expect(page.get_by_role("navigation", name="Studio tools").get_by_role("link", name="Journey map")).to_have_attribute("aria-current", "page")
    expect(page.get_by_role("article", name="Card Flies home")).to_be_visible()
    expect(page.get_by_role("region", name="Unplaced").get_by_role("listitem").filter(has_text="An untold idea")).to_be_visible()
    expect(page.locator(".journey-curve")).to_have_count(2)

    # Two cards share the hospital: the map only offers the merge.
    page.get_by_role("button", name="Select them").click()
    assert not api.moments
    page.get_by_role("button", name="Merge into a shared moment").click()
    moment = page.get_by_role("article", name="Shared moment Flies home")
    expect(moment).to_be_visible()
    expect(moment.get_by_role("button", name="Will")).to_be_visible()
    expect(moment.get_by_role("button", name="Edward")).to_be_visible()
    assert api.moments[0]["scene_id"] == 70
    linked = [(path, match, body) for method, path, match, body in api.calls if method == "PATCH" and path.startswith("/timeline-events/")]
    assert ("/timeline-events/10", "1", {"moment_id": 50}) in linked and ("/timeline-events/11", "1", {"moment_id": 50}) in linked

    # Chronology: the side panel edits a card directly with If-Match; Alt+→ steps it later in story time.
    page.get_by_role("group", name="Axis").get_by_role("button", name="Chronology").click()
    page.get_by_role("article", name="Card Catches the fish").get_by_role("button", name="Catches the fish").click()
    panel = page.get_by_role("complementary", name="Edit Catches the fish")
    panel.get_by_label("Objective").fill("Prove the legend")
    panel.get_by_role("slider", name="Intensity").press("End")
    panel.get_by_role("button", name="Save card").click()
    expect(page.get_by_role("article", name="Card Catches the fish")).to_contain_text("Prove the legend")
    assert any(call[:3] == ("PATCH", "/timeline-events/12", "1") for call in api.calls)
    saved = next(row for row in api.events if row["id"] == 12)
    assert saved["objective"] == "Prove the legend" and saved["intensity"] == 5
    # Past the next column (12, Will's goodbye): the card now comes last in story time.
    page.get_by_role("article", name="Card Catches the fish").get_by_role("button", name="Catches the fish").press("Alt+ArrowRight")
    _until(page, lambda: next(row for row in api.events if row["id"] == 12)["chrono_index"] == 13)

    # The tray places an undated card at the end of story time.
    page.get_by_role("region", name="Unplaced").get_by_role("button", name="Place on axis").click()
    expect(page.get_by_role("article", name="Card An untold idea")).to_be_visible()


def test_journey_reorder_is_a_proposal_until_applied(page: Page) -> None:
    """Moving a scene earlier proposes a reorder (ghosted), Apply approves it, Roll back restores it; a variant re-proposes it."""
    api = _open(page)
    strip = page.get_by_role("region", name="Script strip")
    strip.get_by_role("button", name="Scene 2: EXT. RIVER - DAY").click()
    page.get_by_role("group", name="Move selected scene").get_by_role("button", name="Move scene earlier").click()
    expect(page.get_by_text("Proposed order.")).to_be_visible()
    _until(page, lambda: bool(api.proposals))
    assert api.proposals[0]["proposed_scene_ids"] == [71, 70, 72]
    assert api.order() == [70, 71, 72], "nothing moves before Apply"
    expect(page.locator(".journey-card.ghost")).not_to_have_count(0)
    expect(strip.get_by_role("button", name="Scene 1: EXT. RIVER - DAY")).to_be_visible()

    # A scene keeps its act.
    strip.get_by_role("button", name="Scene 3: INT. FUNERAL HOME - DAY").press("Alt+ArrowLeft")
    expect(page.get_by_role("status").filter(has_text="first scene in its act")).to_be_visible()

    page.get_by_label("Variant name").fill("River first")
    page.get_by_role("button", name="Save as variant").click()
    expect(page.get_by_label("Variants")).to_be_visible()
    _until(page, lambda: bool(api.variants))
    assert api.variants[0]["scene_ids"] == [71, 70, 72]

    page.get_by_role("button", name="Apply reorder").click()
    expect(page.get_by_text("Reorder applied.")).to_be_visible()
    assert api.order() == [71, 70, 72]
    expect(page.locator(".journey-card.ghost")).to_have_count(0)

    page.get_by_role("button", name="Roll back").click()
    expect(page.get_by_text("Reorder applied.")).to_be_hidden()
    _until(page, lambda: api.order() == [70, 71, 72])

    page.get_by_label("Variants").select_option(label="River first")
    page.get_by_role("button", name="Propose variant").click()
    expect(page.get_by_text("Proposed order.")).to_be_visible()
    assert api.proposals[-1]["proposed_scene_ids"] == [71, 70, 72] and api.proposals[-1]["status"] == "proposed"

    # A card's own keyboard move does the same as its scene's: Alt+← on a card in scene 2 proposes again.
    page.get_by_role("button", name="Discard").click()
    expect(page.get_by_text("Proposed order.")).to_be_hidden()
    page.get_by_role("article", name="Card Catches the fish").get_by_role("button", name="Catches the fish").press("Alt+ArrowLeft")
    expect(page.get_by_text("Proposed order.")).to_be_visible()
