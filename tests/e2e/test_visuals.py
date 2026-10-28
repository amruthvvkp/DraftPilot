"""Python Playwright smoke tests for the visual story tools, against a mocked API."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from playwright.sync_api import Page, Route, expect

PROJECT = {"id": 3, "title": "Big Fish", "logline": None, "description": None, "genres": [], "languages": ["English"], "primary_language": "English", "project_instruction": "", "version": 1, "artwork_url": None}
ACTS = [{"id": 4, "screenplay_id": 12, "title": "Act One", "position": 0}, {"id": 5, "screenplay_id": 12, "title": "Act Two", "position": 1}]


def _scene(scene_id: int, act_id: int, index: int, heading: str, intensity: float | None, runtime: int, start: int) -> dict[str, Any]:
    """Build a visuals scene row."""
    return {
        "id": scene_id, "act_id": act_id, "index": index, "heading": heading, "runtime_seconds": runtime, "start_seconds": start,
        "intensity": intensity, "event_count": 0 if intensity is None else 2, "character_ids": [],
    }


VISUALS = {
    "screenplay_id": 12,
    "total_runtime_seconds": 300,
    "acts": [{"id": 4, "title": "Act One", "position": 0}, {"id": 5, "title": "Act Two", "position": 1}],
    "scenes": [
        _scene(21, 4, 0, "EXT. RIVER - DAY", 1, 60, 0),
        _scene(22, 4, 1, "INT. CIRCUS - NIGHT", 4, 120, 60),
        _scene(23, 5, 2, "EXT. WAR - DAY", None, 60, 180),
        _scene(24, 5, 3, "INT. HOSPITAL - NIGHT", -3, 60, 240),
    ],
    "milestones": [{"beat_id": 1, "title": "Meets Sandra", "beat_type": "inciting_incident", "act_id": 4, "scene_id": 22, "scene_index": 1}],
    "characters": [{"id": 7, "name": "Edward", "role": "lead", "moment_count": 3}, {"id": 8, "name": "Will", "role": "", "moment_count": 1}, {"id": 9, "name": "Sandra", "role": "", "moment_count": 2}],
    "edges": [
        {"source": 7, "target": 8, "shared_moments": 1, "shared_scenes": 2, "relations": ["son"]},
        {"source": 7, "target": 9, "shared_moments": 2, "shared_scenes": 1, "relations": []},
    ],
}


def _beat(beat_id: int, title: str, act_id: int | None, position: int, **fields: object) -> dict[str, Any]:
    """Build a typed StoryBeat row."""
    row: dict[str, Any] = {
        "id": beat_id, "project_id": 3, "version": 1, "act_id": act_id, "position": position, "title": title, "summary": "",
        "beat_type": "beat", "status": "planned", "scene_ids": [], "character_ids": [], "source": "writer",
    }
    row.update(fields)
    return row


def _until(page: Page, condition: Callable[[], bool], timeout_ms: int = 5000) -> None:
    """Wait for a condition on the recorded requests, letting the page run meanwhile."""
    for _ in range(timeout_ms // 50):
        if condition():
            return
        page.wait_for_timeout(50)
    raise AssertionError("condition not met in time")


@pytest.fixture
def studio(page: Page) -> dict[str, Any]:
    """Mock the project shell and the visual tools' API; record beat writes."""
    state: dict[str, Any] = {
        "beats": [_beat(1, "Wedding toast", 4, 0, beat_type="inciting_incident", scene_ids=[22]), _beat(2, "The witch", 4, 1), _beat(3, "Spectre", 5, 0)],
        "patches": [],
        "posts": [],
    }

    def respond(route: Route) -> None:
        """Serve the fixture and apply beat writes."""
        request = route.request
        path = request.url.split("/api/v1/projects/3", 1)[-1].split("?", 1)[0]
        payload = request.post_data_json if request.post_data else {}
        result: object = []
        code = 200
        if path == "/workspace":
            result = {"project": PROJECT, "screenplay": {"id": 12, "project_id": 3, "title": "Big Fish", "format": "feature", "status": "draft"}, "acts": ACTS, "scenes": [], "blocks": {}}
        elif path == "/visuals":
            result = VISUALS
        elif path == "/beats" and request.method == "POST":
            state["posts"].append(payload)
            result, code = _beat(100 + len(state["posts"]), payload["title"], payload.get("act_id"), payload.get("position", 0)), 201
        elif path == "/beats":
            result = state["beats"]
        elif path.startswith("/beats/") and request.method == "PATCH":
            row = next(item for item in state["beats"] if item["id"] == int(path.rsplit("/", 1)[-1]))
            state["patches"].append((row["id"], request.headers.get("if-match"), payload))
            row.update(payload, version=row["version"] + 1)
            result = row
        elif path == "/storyline":
            result = {"project_id": 3, "version": 1, "title": "Big Fish", "logline": None, "premise": None, "synopsis": None, "theme": None, "tone": None, "description": None, "story_outline": None}
        elif path == "/events":
            route.fulfill(status=204, body="")
            return
        route.fulfill(status=code, content_type="application/json", body=json.dumps(result))

    page.route("**/api/v1/projects/3/**", respond)
    return state


def test_tension_curve(page: Page, studio: dict[str, Any]) -> None:
    """The tools nav opens the tension curve with its milestones."""
    page.goto("/projects/3/storyline")
    page.get_by_role("navigation", name="Studio tools").get_by_role("link", name="Visuals").click()
    expect(page).to_have_url("/projects/3/visuals/tension")
    expect(page.get_by_role("img", name="Tension curve across 4 scenes, 3 with intensity, 1 milestones")).to_be_visible()
    expect(page.locator(".chart-milestone")).to_contain_text("Meets Sandra")


def test_relationship_graph(page: Page, studio: dict[str, Any]) -> None:
    """The graph ranks links and focuses a character."""
    page.goto("/projects/3/visuals/relationships")
    expect(page.get_by_role("img", name="Relationship graph of 3 characters and 2 links")).to_be_visible()
    expect(page.get_by_role("list", name="Links").get_by_role("listitem").first).to_contain_text("Edward – Sandra")
    page.get_by_role("group", name="Focus a character").get_by_role("button", name="Will").click()
    expect(page.get_by_role("list", name="Links").get_by_role("listitem")).to_have_count(1)


def test_corkboard_keyboard_reorder(page: Page, studio: dict[str, Any]) -> None:
    """Arrow keys move a focused card through versioned beat PATCHes."""
    page.goto("/projects/3/visuals/corkboard")
    act_one = page.get_by_role("region", name="Act One")
    act_one.get_by_role("article", name="The witch, card 2 of 2 in Act One").press("ArrowUp")
    expect(act_one.get_by_role("heading", level=3).first).to_have_text("The witch")
    expect(page.get_by_role("article", name="The witch, card 1 of 2 in Act One")).to_be_focused()
    page.keyboard.press("ArrowRight")
    expect(page.get_by_role("region", name="Act Two").get_by_role("heading", level=3)).to_have_text(["Spectre", "The witch"])
    _until(page, lambda: (2, "2", {"act_id": 5, "position": 1}) in studio["patches"])
    assert (2, "1", {"position": 0}) in studio["patches"]


def test_structure_templates(page: Page, studio: dict[str, Any]) -> None:
    """A template overlays the outline and adds missing beats only after confirmation."""
    page.goto("/projects/3/visuals/structure")
    page.get_by_text("Five acts").click()
    overlay = page.get_by_role("region", name="Five acts overlay")
    expect(overlay.get_by_role("img")).to_have_attribute("aria-label", "Five acts: 7 target beats, 1 matched")
    overlay.get_by_role("button", name="Add 6 missing beats to the outline").click()
    page.get_by_role("dialog").get_by_role("button", name="Add beats").click()
    expect(page.get_by_text("Added 6 target beats to the outline.")).to_be_visible()
    _until(page, lambda: len(studio["posts"]) == 6)
    assert [post["title"] for post in studio["posts"]][:2] == ["Exposition", "Rising action"]


def test_pacing_heatmap(page: Page, studio: dict[str, Any]) -> None:
    """Each act is a row of scene cells sized by runtime."""
    page.goto("/projects/3/visuals/pacing")
    expect(page.get_by_role("listitem", name="Act One").get_by_role("img")).to_have_count(2)
    expect(page.get_by_role("row", name="Act Two")).to_contain_text("-3")
