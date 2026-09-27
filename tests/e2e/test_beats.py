"""Python Playwright journey for the beat board."""

import json

from playwright.sync_api import Page, Route, expect


def test_beat_board_moves_reorders_and_saves_the_outline(page: Page) -> None:
    """Beats move between acts and within an act; saving writes ordered beats and markdown with the version."""
    outline = {
        "id": 5, "project_id": 3, "kind": "outline", "title": "Outline", "content": "", "version": 4, "stale": False, "depends_on": [],
        "artifact_metadata": {"beats": [
            {"act": 1, "title": "Wedding toast", "summary": "Edward steals the night."},
            {"act": 1, "title": "The witch", "summary": "The boys see their deaths."},
            {"act": 2, "title": "Spectre", "summary": "A town too perfect."},
        ]},
    }
    saved: list[tuple[str | None, dict[str, object]]] = []

    def patch(route: Route) -> None:
        """Record the save and bump the version."""
        saved.append((route.request.headers.get("if-match"), route.request.post_data_json))
        outline.update({"version": 5, "artifact_metadata": route.request.post_data_json["metadata"]})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(outline))

    page.route("**/api/v1/projects/3/artifacts", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps([outline])))
    page.route("**/api/v1/projects/3/artifacts/5", patch)
    page.goto("/projects/3/beats")
    act_one, act_two = page.get_by_role("region", name="Act 1"), page.get_by_role("region", name="Act 2")
    expect(act_one.get_by_label("Beat title")).to_have_count(2)
    save = page.get_by_role("button", name="Saved")
    expect(save).to_be_disabled()

    act_one.get_by_role("group", name="Move The witch").get_by_role("button", name="Earlier").click()
    expect(act_one.get_by_label("Beat title").first).to_have_value("The witch")
    act_one.get_by_role("group", name="Move Wedding toast").get_by_role("button", name="Next act").click()
    expect(act_two.get_by_label("Beat title")).to_have_count(2)
    page.get_by_role("button", name="Add beat").click()
    page.get_by_role("button", name="Save outline").click()
    expect(page.get_by_text("Saved as version 5.")).to_be_visible()

    if_match, body = saved[0]
    assert if_match == "4"
    beats = body["metadata"]["beats"]  # type: ignore[index]
    assert [(beat["act"], beat["title"], beat["sequence"]) for beat in beats] == [
        (1, "The witch", 1), (1, "New beat", 2), (2, "Wedding toast", 3), (2, "Spectre", 4),
    ]
    assert "## Act 2\n- **Wedding toast**" in str(body["content"])
