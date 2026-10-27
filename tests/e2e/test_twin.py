"""Python Playwright journey for the Story twin page."""

import json
import re

from playwright.sync_api import Page, Route, expect


def _character(row_id: int, name: str, **fields: object) -> dict[str, object]:
    """Build a typed Character row as the twin returns it."""
    row: dict[str, object] = {
        "id": row_id, "project_id": 7, "version": 1, "position": 0, "name": name, "role": "", "summary": "", "bio": "", "want": "", "need": "",
        "motive": "", "objective": "", "flaw": "", "arc_summary": "", "voice": "", "notes": "", "aliases": [], "tags": [], "cue": name.upper(),
        "dialogue_lines": 0, "scene_ids": [], "source": "twin", "writer_edited": False,
    }
    row.update(fields)
    return row


def _location(row_id: int, name: str, **fields: object) -> dict[str, object]:
    """Build a typed Location row as the twin returns it."""
    row: dict[str, object] = {
        "id": row_id, "project_id": 7, "version": 1, "position": 0, "name": name, "description": "", "visual_notes": "", "notes": "",
        "heading_location": name.upper(), "int_ext": [], "times": [], "scene_ids": [], "source": "twin", "writer_edited": False,
    }
    row.update(fields)
    return row


def test_story_twin_shows_the_cast_and_keeps_the_writers_note(page: Page) -> None:
    """Characters are ranked by dialogue; a writer note is saved with the row's version; refresh re-derives."""
    twin = {
        "screenplay_id": 3,
        "characters": [_character(1, "Edward", dialogue_lines=307, scene_ids=[1, 2, 3]), _character(2, "Will", dialogue_lines=145, scene_ids=[2])],
        "locations": [_location(3, "Bloom House", int_ext=["INT", "EXT"], times=["DAY"], scene_ids=[4])],
        "canon": [],
        "brief": "",
    }
    patches: list[tuple[str | None, dict[str, object]]] = []
    refreshed: list[bool] = []

    def patch(route: Route) -> None:
        """Save the writer's note and mark the row as theirs."""
        patches.append((route.request.headers.get("if-match"), route.request.post_data_json))
        row = twin["characters"][1]  # type: ignore[index]
        row.update({"summary": route.request.post_data_json["summary"], "version": 2, "writer_edited": True})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(row))

    def refresh(route: Route) -> None:
        """Re-derive the twin."""
        refreshed.append(True)
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"characters": 2, "locations": 1, "removed": 0}))

    page.route("**/api/v1/projects/7/twin", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(twin)))
    page.route("**/api/v1/projects/7/twin/refresh", refresh)
    page.route("**/api/v1/projects/7/characters/2", patch)
    page.route("**/api/v1/projects/7/events", lambda route: route.fulfill(status=204, body=""))

    page.goto("/projects/7/twin")
    characters = page.get_by_role("region", name="Characters")
    expect(characters.get_by_text("307 lines · 3 scenes")).to_be_visible()
    note = characters.get_by_label("Note on Will")
    note.fill("Wants the truth, needs the story.")
    note.blur()
    expect(characters.get_by_title("You wrote or edited this")).to_be_visible()
    assert patches == [("1", {"summary": "Wants the truth, needs the story."})]
    expect(page.get_by_role("region", name="Locations").get_by_text("INT/EXT · DAY · 1 scenes")).to_be_visible()
    characters.get_by_role("link", name="Will").click()
    expect(page).to_have_url(re.compile(r"/projects/7/characters/2$"))
    page.go_back()
    page.get_by_label("Filter the Story twin").fill("edw")
    expect(characters.get_by_text("Will", exact=True)).to_have_count(0)
    page.get_by_role("button", name="Refresh from the draft").click()
    expect(page.get_by_role("button", name="Refresh from the draft")).to_be_enabled()
    assert refreshed == [True]
