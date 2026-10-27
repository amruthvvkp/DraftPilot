"""Real-stack browser journey (no mocks): develop a screenplay end to end by hand, without any agent.

Project → Storyline → Characters (profiles, timelines, a relationship) → Outline (acts, beats) →
first scene from a beat → blocks → Fountain export. Run with the stack up:

    uv run pytest tests/e2e/test_manual_journey.py -m stack

It creates its own project and deletes it afterwards; it never touches other projects.
"""

import os
import re
import subprocess
from collections.abc import Iterator

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.stack
TITLE = "Manual journey · Lantern House"
HEADING = "INT. LANTERN HOUSE - NIGHT"


def _token() -> str:
    """Return the stack's API token (env E2E_API_TOKEN, else read from the running ui container)."""
    if token := os.environ.get("E2E_API_TOKEN"):
        return token
    result = subprocess.run(["docker", "compose", "exec", "-T", "ui", "printenv", "API__TOKEN"], capture_output=True, text=True, check=False)
    return result.stdout.strip()


@pytest.fixture
def signed_in(page: Page, base_url: str) -> Iterator[Page]:
    """Sign the browser in and delete every project this journey created, even on failure."""
    page.goto(base_url)
    token = _token()
    if token:
        assert page.request.post(f"{base_url}/api/v1/auth/session", data={"token": token}).ok
    before = {project["id"] for project in page.request.get(f"{base_url}/api/v1/projects").json()}
    yield page
    for project in page.request.get(f"{base_url}/api/v1/projects").json():
        if project["id"] not in before and project["title"].startswith("Manual journey"):
            page.request.delete(f"{base_url}/api/v1/projects/{project['id']}")
    for deleted in page.request.get(f"{base_url}/api/v1/projects/deleted").json():
        if deleted["title"].startswith("Manual journey"):
            page.request.post(f"{base_url}/api/v1/projects/deleted/{deleted['project_id']}/dismiss")


def _step(page: Page, name: str) -> None:
    """Open a step of the guided stepper."""
    page.get_by_role("navigation", name="Project steps").get_by_role("link", name=re.compile(name)).click()


def _add_character(page: Page, name: str, role: str, profile: dict[str, str], event: tuple[str, str, str]) -> None:
    """Create a character, fill their profile and add one timeline event."""
    page.get_by_label("New character name").fill(name)
    page.get_by_label("New character role").fill(role)
    page.get_by_role("button", name="Add character").click()
    detail = page.get_by_role("region", name=f"Character {name}")
    expect(detail).to_be_visible()
    for label, value in profile.items():
        detail.get_by_label(label, exact=True).fill(value)
    detail.get_by_role("button", name="Save profile").click()
    expect(detail.get_by_text("Profile saved.")).to_be_visible()

    title, story_time, objective = event
    timeline = page.get_by_role("region", name=f"{name} timeline")
    form = timeline.get_by_role("form", name="New timeline event")
    form.get_by_label("Event", exact=True).fill(title)
    form.get_by_label("Story time").fill(story_time)
    form.get_by_label("Objective here").fill(objective)
    form.get_by_role("button", name="Add event").click()
    expect(timeline.get_by_text(title, exact=True)).to_be_visible()


def test_manual_screenplay_from_project_to_fountain(signed_in: Page, base_url: str) -> None:
    """A writer builds a screenplay with no agent: every stage persists and the export carries it."""
    page = signed_in

    # Project, through the wizard.
    page.goto(f"{base_url}/projects")
    page.get_by_role("button", name="New project").first.click()
    wizard = page.locator(".wizard")
    wizard.get_by_label("Project title").fill(TITLE)
    wizard.get_by_role("button", name="Drama", exact=True).click()
    wizard.get_by_role("button", name="Continue").click()
    wizard.get_by_role("button", name="Continue").click()
    wizard.get_by_role("button", name="Continue").click()
    wizard.get_by_role("button", name="Create project", exact=False).click()
    expect(page).to_have_url(re.compile(r"/projects/\d+$"), timeout=30_000)
    project_id = int(page.url.rstrip("/").rsplit("/", 1)[-1])
    expect(page.get_by_text("Your first scene starts here.")).to_be_visible()

    # Storyline.
    _step(page, "Storyline")
    storyline = {
        "Logline": "A woman inherits a house that remembers every lie told inside it.",
        "Premise": "What if a house kept score of a family's secrets?",
        "Synopsis": "Mira returns to sell the family house and finds it will not let her leave until the truth is told.",
        "Theme": "Truth outlives the people who hide it.",
        "Tone": "Quiet, eerie, warm underneath.",
    }
    for label, value in storyline.items():
        page.get_by_label(label, exact=True).fill(value)
    page.get_by_role("button", name="Save storyline").click()
    expect(page.get_by_text("Storyline saved.")).to_be_visible()
    expect(page.get_by_role("navigation", name="Project steps")).to_contain_text("Logline set · 5/5")
    page.reload()
    expect(page.get_by_label("Theme", exact=True)).to_have_value(storyline["Theme"])

    # Characters: two profiles, each with a timeline event, and a relationship.
    _step(page, "Characters")
    _add_character(page, "Mira", "protagonist",
                   {"Want": "To sell the house", "Need": "To forgive her mother", "Motive": "Guilt", "Objective": "Leave by Sunday", "Arc": "From flight to reckoning"},
                   ("Arrives at the house", "Day 1, dusk", "Get in and out"))
    _add_character(page, "Tom", "mentor",
                   {"Motive": "Loyalty to the family", "Objective": "Keep the ledger hidden"},
                   ("Hides the ledger", "Day 1, night", "Protect Mira"))
    relationships = page.get_by_role("region", name="Relationships")
    relationships.get_by_label("Related character").select_option(label="Mira")
    relationships.get_by_label("Relation", exact=True).fill("godfather of")
    relationships.get_by_role("button", name="Add relationship").click()
    expect(relationships.get_by_label("Relation between Tom and Mira")).to_have_value("godfather of")
    expect(page.get_by_role("navigation", name="Project steps")).to_contain_text("2 · 2 with motive & objective")

    # Outline: a second act and a beat in each act, one linked to a character.
    _step(page, "Outline")
    act_one = page.get_by_role("region", name="Act One")
    expect(act_one).to_be_visible()
    page.get_by_label("New act title").fill("Act Two")
    page.get_by_role("button", name="Add act").click()
    act_two = page.get_by_role("region", name="Act Two")
    expect(act_two).to_be_visible()
    act_one.get_by_label("New beat in Act One").fill("Mira arrives")
    act_one.get_by_role("button", name="Add beat to Act One").click()
    act_two.get_by_label("New beat in Act Two").fill("The ledger")
    act_two.get_by_role("button", name="Add beat to Act Two").click()
    beat = page.get_by_role("article", name="Beat Mira arrives")
    expect(beat).to_be_visible()
    beat.get_by_label("Summary of Mira arrives").fill("She lets herself in; the house is warm.")
    beat.get_by_label("Summary of Mira arrives").blur()
    beat.locator("summary").click()
    beat.get_by_role("group", name="Characters in Mira arrives").get_by_label("Mira").check()
    expect(beat.locator("summary")).to_contain_text("1 characters")

    # The first scene, created from the beat.
    beat.get_by_label("Scene heading for Mira arrives").fill(HEADING)
    beat.get_by_role("button", name="Create scene from beat").click()
    open_scene = beat.get_by_role("link", name=f"Open {HEADING} in the script")
    expect(open_scene).to_be_visible(timeout=30_000)
    expect(page.get_by_role("navigation", name="Project steps")).to_contain_text("2 beats · 1 linked")

    # Script: write blocks into the new scene.
    open_scene.click()
    expect(page.get_by_label("Edit scene heading")).to_have_value(HEADING)
    for element, text in (("action", "Rain drums on the roof. MIRA stands in the doorway."), ("character", "MIRA"), ("dialogue", "Hello, house.")):
        page.get_by_label("New screenplay element").select_option(element)
        page.get_by_label("New element text").fill(text)
        page.get_by_role("button", name="＋ Add element").click()
        expect(page.get_by_label(f"Edit {element}").last).to_have_value(text, timeout=30_000)
    page.reload()
    expect(page.get_by_label("Edit dialogue")).to_have_value("Hello, house.")

    # What the agents will see now.
    page.get_by_role("navigation", name="Studio tools").get_by_role("link", name="Context map").click()
    brief = page.get_by_role("region", name="Agent brief")
    expect(brief).to_contain_text(f"Logline: {storyline['Logline']}", timeout=30_000)
    expect(brief).to_contain_text("Mira (protagonist")

    # Export Fountain.
    _step(page, "Script")
    href = page.get_by_role("link", name="Fountain").get_attribute("href")
    assert href is not None and href.startswith(f"/api/v1/projects/{project_id}/screenplays/")
    export = page.request.get(f"{base_url}{href}")
    assert export.ok
    fountain = export.text()
    for expected in (HEADING, "MIRA", "Hello, house.", "Rain drums on the roof."):
        assert expected in fountain, f"{expected!r} missing from the Fountain export"
