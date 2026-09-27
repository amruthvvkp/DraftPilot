"""Browser smoke test against the real stack (no mocks): Big Fish from import to cleanup.

Run on demand with the stack up:  uv run pytest tests/e2e -m stack
It creates, edits and finally deletes its own projects; it never touches other projects.
"""

import os
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.stack
BIG_FISH = Path(__file__).parents[1] / "test_screenplays" / "Big-Fish.fountain"


def _token() -> str:
    """Return the stack's API token (env E2E_API_TOKEN, else read from the running ui container)."""
    if token := os.environ.get("E2E_API_TOKEN"):
        return token
    result = subprocess.run(["docker", "compose", "exec", "-T", "ui", "printenv", "API__TOKEN"], capture_output=True, text=True, check=False)
    return result.stdout.strip()


def _open_imported_draft(page: Page) -> None:
    """Switch the workspace to the imported Big Fish draft."""
    picker = page.get_by_label("Screenplay draft")
    expect(picker).to_be_visible(timeout=30_000)
    value = picker.locator("option", has_text="Imported").first.get_attribute("value")
    assert value is not None
    picker.select_option(value=value)


@pytest.fixture
def signed_in(page: Page, base_url: str) -> Iterator[Page]:
    """Sign the browser in and delete every project this test created, even on failure."""
    page.goto(base_url)
    token = _token()
    if token:
        assert page.request.post(f"{base_url}/api/v1/auth/session", data={"token": token}).ok
    before = {project["id"] for project in page.request.get(f"{base_url}/api/v1/projects").json()}
    yield page
    for project in page.request.get(f"{base_url}/api/v1/projects").json():
        if project["id"] not in before and project["title"].startswith("Smoke · Big Fish"):
            page.request.delete(f"{base_url}/api/v1/projects/{project['id']}")
    for deleted in page.request.get(f"{base_url}/api/v1/projects/deleted").json():
        if deleted["title"].startswith("Smoke · Big Fish"):
            page.request.post(f"{base_url}/api/v1/projects/deleted/{deleted['project_id']}/dismiss")


def test_big_fish_from_import_to_cleanup(signed_in: Page, base_url: str) -> None:
    """Import Big Fish, edit it, see the Story twin, open the room, export, duplicate and delete."""
    page = signed_in
    project = page.request.post(f"{base_url}/api/v1/projects", data={"title": "Smoke · Big Fish", "genres": ["Drama"]}).json()
    page.goto(f"{base_url}/projects/{project['id']}")

    # Import through the workspace's file picker.
    page.locator("input[type=file]").set_input_files(str(BIG_FISH))
    expect(page.get_by_text("191 scenes", exact=False)).to_be_visible(timeout=60_000)
    _open_imported_draft(page)
    expect(page.get_by_text("This is a Southern story", exact=False)).to_be_visible(timeout=30_000)

    # Edit the opening action line; it saves and survives a reload.
    editor = page.get_by_label("Edit action").first
    editor.fill("This is a Southern story, full of lies and fabrications. (smoke edit)")
    editor.blur()
    page.wait_for_timeout(1500)
    page.reload()
    _open_imported_draft(page)
    expect(page.get_by_text("(smoke edit)", exact=False)).to_be_visible(timeout=30_000)
    expect(page.get_by_role("separator", name="Page break").first).to_be_visible()

    # The Story twin knows the cast (refresh derives it now rather than waiting for the debounce).
    page.get_by_role("navigation", name="Project tools").get_by_role("link", name="Story twin").click()
    page.get_by_role("button", name="Refresh from the draft").click()
    characters = page.get_by_role("region", name="Characters")
    expect(characters.get_by_text("Edward", exact=True)).to_be_visible(timeout=60_000)
    expect(characters.get_by_text("307 lines · 87 scenes", exact=True)).to_be_visible()

    # The writers' room lists its workflows.
    page.goto(f"{base_url}/projects/{project['id']}/room")
    expect(page.get_by_role("tab", name=re.compile("Rewrite a scene"))).to_be_visible()
    expect(page.get_by_role("region", name="Room chat")).to_be_visible()

    # Exports render.
    screenplays = page.request.get(f"{base_url}/api/v1/projects/{project['id']}/workspace").json()["screenplays"]
    imported = next(item for item in screenplays if "Imported" in item["title"])
    pdf = page.request.get(f"{base_url}/api/v1/projects/{project['id']}/screenplays/{imported['id']}/exports/pdf")
    assert pdf.ok and pdf.body()[:4] == b"%PDF"

    # Duplicate and delete from the vault.
    page.goto(f"{base_url}/projects")
    page.get_by_role("button", name="Actions for Smoke · Big Fish").first.click()
    page.get_by_role("menuitem", name="Duplicate").click()
    expect(page.get_by_text("Duplicated as “Smoke · Big Fish (copy)”.")).to_be_visible(timeout=60_000)
    page.get_by_role("button", name="Actions for Smoke · Big Fish (copy)").click()
    page.get_by_role("menuitem", name="Delete…").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Project title to confirm").fill("Smoke · Big Fish (copy)")
    dialog.get_by_role("button", name="Delete project").click()
    expect(page.get_by_text("A backup was kept", exact=False)).to_be_visible(timeout=60_000)
    expect(page.get_by_role("region", name="Recently deleted").get_by_text("Smoke · Big Fish (copy)").first).to_be_visible()
