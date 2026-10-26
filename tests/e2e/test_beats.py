"""Python Playwright journey for the Outline (the old beat-board URL keeps working)."""

import json
from typing import Any

from playwright.sync_api import Page, Route, expect


def _beat(beat_id: int, title: str, act_id: int | None, position: int, **fields: object) -> dict[str, Any]:
    """Build a typed StoryBeat row."""
    row: dict[str, Any] = {
        "id": beat_id, "project_id": 3, "version": 1, "act_id": act_id, "position": position, "title": title, "summary": "",
        "beat_type": "beat", "status": "planned", "scene_ids": [], "character_ids": [], "source": "writer",
    }
    row.update(fields)
    return row


def test_outline_moves_reorders_links_and_creates_scenes(page: Page) -> None:
    """Beats move within and between acts through versioned PATCHes; a beat becomes a scene; acts can be added."""
    acts = [{"id": 4, "screenplay_id": 12, "title": "Act One", "position": 0}, {"id": 5, "screenplay_id": 12, "title": "Act Two", "position": 1}]
    scenes: list[dict[str, Any]] = []
    beats = [_beat(1, "Wedding toast", 4, 0, summary="Edward steals the night."), _beat(2, "The witch", 4, 1), _beat(3, "Spectre", 5, 0)]
    patches: list[tuple[int, str | None, dict[str, Any]]] = []
    conflicts: list[int] = []
    project = {"id": 3, "title": "Big Fish", "logline": None, "description": None, "genres": [], "languages": ["English"], "primary_language": "English", "project_instruction": "", "version": 1, "artwork_url": None}

    def respond(route: Route) -> None:
        """Serve the outline fixture and apply its writes."""
        request = route.request
        path = request.url.split("/api/v1/projects/3", 1)[-1].split("?", 1)[0]
        payload = request.post_data_json if request.post_data else {}
        result: object = []
        code = 200
        if path == "/workspace":
            result = {"project": project, "screenplay": {"id": 12, "project_id": 3, "title": "Big Fish", "format": "feature", "status": "draft"}, "acts": acts, "scenes": scenes, "blocks": {}}
        elif path == "/beats" and request.method == "POST":
            row = _beat(10 + len(beats), payload["title"], payload["act_id"], payload["position"])
            beats.append(row)
            result, code = row, 201
        elif path == "/beats":
            result = beats
        elif path.startswith("/beats/") and request.method == "PATCH":
            row = next(item for item in beats if item["id"] == int(path.rsplit("/", 1)[-1]))
            patches.append((row["id"], request.headers.get("if-match"), payload))
            if request.headers.get("if-match") != str(row["version"]):
                conflicts.append(row["id"])
                route.fulfill(status=409, content_type="application/json", body=json.dumps({"detail": "Beat has changed"}))
                return
            row.update(payload, version=row["version"] + 1)
            result = row
        elif path == "/acts" and request.method == "POST":
            row = {"id": 6, "screenplay_id": 12, "title": payload["title"], "position": len(acts)}
            acts.append(row)
            result, code = row, 201
        elif path == "/scenes" and request.method == "POST":
            row = {"id": 70, "act_id": payload["act_id"], "heading": payload["heading"], "position": 0, "body": "", "version": 1, "scene_instruction": ""}
            scenes.append(row)
            result, code = row, 201
        elif path == "/storyline":
            result = {"project_id": 3, "version": 1, "title": "Big Fish", "logline": None, "premise": None, "synopsis": None, "theme": None, "tone": None, "description": None, "story_outline": None}
        elif path == "/events":
            route.fulfill(status=204, body="")
            return
        route.fulfill(status=code, content_type="application/json", body=json.dumps(result))

    page.route("**/api/v1/projects/3/**", respond)
    page.goto("/projects/3/beats")
    act_one, act_two = page.get_by_role("region", name="Act One"), page.get_by_role("region", name="Act Two")
    expect(act_one.get_by_label("Beat title")).to_have_count(2)
    expect(page.get_by_role("navigation", name="Project steps")).to_contain_text("3 beats · 0 linked")

    act_one.get_by_role("group", name="Move The witch").get_by_role("button", name="Earlier").click()
    expect(act_one.get_by_label("Beat title").first).to_have_value("The witch")
    act_one.get_by_role("group", name="Move Wedding toast").get_by_role("button", name="Next act").click()
    expect(act_two.get_by_label("Beat title")).to_have_count(2)
    assert (1, "2", {"act_id": 5, "position": 1}) in patches

    # Keyboard: the handle's arrow keys move a beat too.
    act_two.get_by_role("button", name="Reorder Spectre").press("ArrowLeft")
    expect(act_one.get_by_label("Beat title")).to_have_count(2)

    act_two.get_by_label("New beat in Act Two").fill("Fish story")
    act_two.get_by_role("button", name="Add beat to Act Two").click()
    expect(act_two.get_by_label("Beat title")).to_have_count(2)

    card = page.get_by_role("article", name="Beat Fish story")
    card.locator("summary").click()
    card.get_by_label("Scene heading for Fish story").fill("EXT. RIVER - DAY")
    card.get_by_role("button", name="Create scene from beat").click()
    expect(card.get_by_role("link", name="Open EXT. RIVER - DAY in the script")).to_be_visible()
    assert scenes[0]["act_id"] == 5
    assert next(item for item in beats if item["title"] == "Fish story")["scene_ids"] == [70]

    page.get_by_label("New act title").fill("Act Three")
    page.get_by_role("button", name="Add act").click()
    expect(page.get_by_role("region", name="Act Three")).to_be_visible()
    assert patches and all(if_match for _, if_match, _ in patches), "every beat write carries If-Match"
    assert not conflicts, "sequential beat writes never race into a 409"
