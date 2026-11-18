"""Journey map against the real stack (no mocks): two characters, a shared moment, a scene dragged earlier, apply, roll back.

Run on demand with the stack up:  uv run pytest tests/e2e/test_journey_stack.py -m stack
It creates and finally deletes its own project; it never touches other projects.
"""

import os
import subprocess
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.stack
TITLE = "Journey · e2e"


def _token() -> str:
    """Return the stack's API token (env E2E_API_TOKEN, else read from the running ui container)."""
    if token := os.environ.get("E2E_API_TOKEN"):
        return token
    result = subprocess.run(["docker", "compose", "exec", "-T", "ui", "printenv", "API__TOKEN"], capture_output=True, text=True, check=False)
    return result.stdout.strip()


@pytest.fixture
def project(page: Page, base_url: str) -> Iterator[dict[str, Any]]:
    """Sign in if the API asks for it, create a project with three scenes and two characters, and delete it afterwards."""
    page.goto(base_url)
    if page.request.get(f"{base_url}/api/v1/projects").status == 401:
        assert page.request.post(f"{base_url}/api/v1/auth/session", data={"token": _token()}).ok
    api = f"{base_url}/api/v1"
    created = page.request.post(f"{api}/projects", data={"title": TITLE, "genres": ["Drama"]}).json()
    pid = created["id"]
    try:
        workspace = page.request.get(f"{api}/projects/{pid}/workspace").json()
        act = workspace["acts"][0]["id"] if workspace["acts"] else page.request.post(f"{api}/projects/{pid}/acts", data={"title": "Act One"}).json()["id"]
        scenes = [page.request.post(f"{api}/projects/{pid}/scenes", data={"heading": heading, "act_id": act}).json()
                  for heading in ("INT. HOSPITAL - NIGHT", "EXT. RIVER - DAY", "INT. CIRCUS TENT - NIGHT")]
        will = page.request.post(f"{api}/projects/{pid}/characters", data={"name": "Will"}).json()
        edward = page.request.post(f"{api}/projects/{pid}/characters", data={"name": "Edward"}).json()
        for character, title, scene, intensity in ((will, "Flies home", 0, -2), (edward, "Tells the witch story", 0, 3), (edward, "Joins the circus", 2, 4)):
            response = page.request.post(f"{api}/projects/{pid}/timeline-events", data={"character_id": character["id"], "title": title, "scene_id": scenes[scene]["id"], "intensity": intensity})
            assert response.ok, response.text()
        yield {"id": pid, "api": f"{api}/projects/{pid}", "scenes": [scene["id"] for scene in scenes], "screenplay": workspace["screenplay"]["id"]}
    finally:
        page.request.delete(f"{api}/projects/{pid}")
        for deleted in page.request.get(f"{api}/projects/deleted").json():
            if deleted["title"] == TITLE:
                page.request.post(f"{api}/projects/deleted/{deleted['project_id']}/dismiss")


def _order(page: Page, project: dict[str, Any]) -> list[int]:
    """Return the scene order the server holds."""
    return [scene["id"] for scene in page.request.get(f"{project['api']}/workspace").json()["scenes"]]


def test_journey_shared_moment_and_reversible_reorder(page: Page, base_url: str, project: dict[str, Any]) -> None:
    """Merge two characters' cards into a shared moment, drag a scene earlier, apply the proposal and roll it back."""
    first, second, third = project["scenes"]
    page.set_viewport_size({"width": 1600, "height": 1000})
    page.goto(f"{base_url}/projects/{project['id']}")
    page.get_by_role("navigation", name="Studio tools").get_by_role("link", name="Journey map").click()
    expect(page.get_by_role("article", name="Card Flies home")).to_be_visible(timeout=30_000)
    expect(page.get_by_role("article", name="Card Tells the witch story")).to_be_visible()

    # The shared moment is the writer's explicit choice: select both cards, then merge.
    page.get_by_label("Select Flies home for merge").check()
    page.get_by_label("Select Tells the witch story for merge").check()
    page.get_by_role("button", name="Merge into a shared moment").click()
    moment = page.get_by_role("article", name="Shared moment Flies home")
    expect(moment).to_be_visible()
    expect(moment.get_by_role("button", name="Will")).to_be_visible()
    expect(moment.get_by_role("button", name="Edward")).to_be_visible()
    moments = page.request.get(f"{project['api']}/moments").json()
    assert len(moments) == 1 and moments[0]["scene_id"] == first
    linked = [event for event in page.request.get(f"{project['api']}/timeline-events").json() if event["moment_id"] == moments[0]["id"]]
    assert sorted(event["title"] for event in linked) == ["Flies home", "Tells the witch story"]

    # Drag the circus scene earlier in the script strip: a proposal, shown as ghosts; the script is unchanged.
    strip = page.get_by_role("region", name="Script strip")
    source = strip.get_by_role("button", name="Scene 3: INT. CIRCUS TENT - NIGHT").bounding_box()
    target = strip.get_by_role("button", name="Scene 2: EXT. RIVER - DAY").bounding_box()
    assert source and target
    page.mouse.move(source["x"] + source["width"] / 2, source["y"] + source["height"] / 2)
    page.mouse.down()
    page.mouse.move(target["x"] + target["width"] / 2, target["y"] + target["height"] / 2, steps=12)
    page.mouse.move(target["x"] + target["width"] / 3, target["y"] + target["height"] / 2, steps=4)
    page.mouse.up()
    expect(page.get_by_text("Proposed order.")).to_be_visible()
    expect(strip.get_by_role("button", name="Scene 2: INT. CIRCUS TENT - NIGHT")).to_be_visible()
    expect(page.locator(".journey-card.ghost")).not_to_have_count(0)
    assert _order(page, project) == [first, second, third]

    page.get_by_role("button", name="Apply reorder").click()
    expect(page.get_by_text("Reorder applied.")).to_be_visible()
    assert _order(page, project) == [first, third, second]
    expect(page.locator(".journey-card.ghost")).to_have_count(0)

    page.get_by_role("button", name="Roll back").click()
    expect(page.get_by_text("Reorder applied.")).to_be_hidden()
    expect(strip.get_by_role("button", name="Scene 3: INT. CIRCUS TENT - NIGHT")).to_be_visible()
    assert _order(page, project) == [first, second, third]
