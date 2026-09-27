"""Python Playwright journey for the Story twin page."""

import json

from playwright.sync_api import Page, Route, expect


def _node(node_id: int, kind: str, label: str, **metadata: object) -> dict[str, object]:
    """Build a derived Story-twin node."""
    return {"id": node_id, "project_id": 7, "kind": kind, "label": label, "description": f"{label} (derived)", "version": 1,
            "node_metadata": {"source": "twin_keeper", **metadata}}


def test_story_twin_shows_the_cast_and_keeps_the_writers_note(page: Page) -> None:
    """Characters are ranked by dialogue; a writer note is saved with the node's version; refresh re-derives."""
    twin = {
        "screenplay_id": 3,
        "characters": [_node(1, "character", "Edward", dialogue_lines=307, scene_ids=[1, 2, 3]), _node(2, "character", "Will", dialogue_lines=145, scene_ids=[2])],
        "locations": [_node(3, "location", "Bloom House", int_ext=["INT", "EXT"], times=["DAY"], scene_ids=[4])],
        "canon": [],
        "brief": "",
    }
    patches: list[tuple[str | None, dict[str, object]]] = []
    refreshed: list[bool] = []

    def patch(route: Route) -> None:
        """Save the writer's note and mark the node as theirs."""
        patches.append((route.request.headers.get("if-match"), route.request.post_data_json))
        node = twin["characters"][1]
        node.update({"description": route.request.post_data_json["description"], "version": 2})
        node["node_metadata"]["writer_edited"] = True  # type: ignore[index]
        route.fulfill(status=200, content_type="application/json", body=json.dumps(node))

    def refresh(route: Route) -> None:
        """Re-derive the twin."""
        refreshed.append(True)
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"characters": 2, "locations": 1, "removed": 0}))

    page.route("**/api/v1/projects/7/twin", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(twin)))
    page.route("**/api/v1/projects/7/twin/refresh", refresh)
    page.route("**/api/v1/projects/7/knowledge-graph/nodes/2", patch)
    page.route("**/api/v1/projects/7/events", lambda route: route.fulfill(status=204, body=""))

    page.goto("/projects/7/twin")
    characters = page.get_by_role("region", name="Characters")
    expect(characters.get_by_text("307 lines · 3 scenes")).to_be_visible()
    note = characters.get_by_label("Note on Will")
    note.fill("Wants the truth, needs the story.")
    note.blur()
    expect(characters.get_by_text("your note")).to_be_visible()
    assert patches == [("1", {"description": "Wants the truth, needs the story."})]
    expect(page.get_by_role("region", name="Locations").get_by_text("INT/EXT · DAY · 1 scenes")).to_be_visible()
    page.get_by_label("Filter the Story twin").fill("edw")
    expect(characters.get_by_text("Will", exact=True)).to_have_count(0)
    page.get_by_role("button", name="Refresh from the draft").click()
    expect(page.get_by_role("button", name="Refresh from the draft")).to_be_enabled()
    assert refreshed == [True]
