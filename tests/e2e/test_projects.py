"""Python Playwright journeys for the React project studio."""

import json
import re

from playwright.sync_api import Page, Route, expect


def mock_projects_api(page: Page) -> None:
    """Route project API calls to an in-memory browser fixture."""
    project = {
        "id": 9001,
        "title": "Playwright story",
        "logline": "A mocked project.",
        "description": "",
        "genres": ["Drama"],
        "languages": ["English"],
        "artwork_url": None,
    }

    def handle(route: Route) -> None:
        """Fulfill a project API request without touching Postgres."""
        request = route.request
        if request.method == "POST":
            payload = request.post_data_json
            if payload.get("title") == "Playwright story":
                assert payload["references"] == [{"kind": "film", "label": "Pather Panchali", "url": "https://example.test/pather-panchali", "note": None}]
            route.fulfill(status=201, content_type="application/json", body=json.dumps(project))
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps([]))

    page.route("**/api/v1/projects", handle)


def test_project_vault_requires_title_before_creation(page: Page) -> None:
    """Show the project wizard and reject an empty title."""
    mock_projects_api(page)
    page.goto("/projects")
    expect(page.get_by_role("heading", name="Projects")).to_be_visible()
    page.get_by_role("button", name="New project").first.click()
    expect(page.get_by_role("heading", name="Find the shape of your story.")).to_be_visible()
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_text("Give your project a title before continuing.")).to_be_visible()


def test_create_project_from_react_wizard(page: Page) -> None:
    """Create a project through the visible React workflow."""
    mock_projects_api(page)
    workspace = {
        "project": {
            "id": 9001,
            "title": "Playwright story",
            "logline": "A mocked project.",
            "description": "",
            "genres": ["Drama"],
            "languages": ["English"],
            "primary_language": "English",
            "project_instruction": "",
            "version": 1,
            "artwork_url": None,
        },
        "screenplay": {"id": 12, "project_id": 9001, "title": "Playwright story", "format": "feature", "status": "draft"},
        "acts": [{"id": 4, "screenplay_id": 12, "title": "Act One", "position": 0}],
        "scenes": [],
        "blocks": {},
    }
    page.route("**/api/v1/projects/9001/workspace", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(workspace)
    ))
    page.route("**/api/v1/projects/9001/agent-proposals", lambda route: route.fulfill(
        status=200, content_type="application/json", body="[]"
    ))
    page.route("**/api/v1/projects/9001/copilot/messages", lambda route: route.fulfill(
        status=200, content_type="application/json", body="[]"
    ))
    page.route("**/api/v1/agents/roles", lambda route: route.fulfill(
        status=200, content_type="application/json", body="[]"
    ))
    page.route("**/api/v1/settings/providers", lambda route: route.fulfill(
        status=200, content_type="application/json", body="[]"
    ))
    page.goto("/projects")
    page.get_by_role("button", name="New project").first.click()
    wizard = page.locator(".wizard")
    page.get_by_label("Project title").fill("Playwright story")
    page.get_by_role("button", name="Drama").click()
    wizard.get_by_role("button", name="Continue").click()
    expect(wizard.get_by_label("Description")).to_be_visible()
    wizard.get_by_role("button", name="Continue").click()
    expect(wizard.get_by_role("group", name="Typed creative references")).to_be_visible()
    wizard.get_by_role("button", name="Add typed reference").click()
    wizard.get_by_role("textbox", name="Reference", exact=True).fill("Pather Panchali")
    wizard.get_by_label("URL").fill("https://example.test/pather-panchali")
    wizard.get_by_role("button", name="Continue").click()
    expect(wizard.get_by_text("READY TO BEGIN")).to_be_visible()
    wizard.get_by_role("button", name="Create project", exact=False).click()
    expect(page).to_have_url(re.compile(r"/projects/9001$"))
    expect(page.get_by_role("heading", name="Playwright story")).to_be_visible()


def test_primary_language_is_not_a_translation_target(page: Page) -> None:
    """Keep the primary screenplay language separate from dialogue translations."""
    mock_projects_api(page)
    page.goto("/projects")
    page.get_by_role("button", name="New project").first.click()
    wizard = page.locator(".wizard")
    wizard.get_by_label("Project title").fill("Hindi story")
    wizard.get_by_role("button", name="Continue").click()
    expect(wizard.get_by_role("button", name="Film Noir", exact=True)).to_be_visible()
    expect(wizard.get_by_role("button", name="Psychological", exact=True)).to_be_visible()
    primary = wizard.get_by_label("Primary screenplay language")
    primary.select_option(label="Hindi")
    hindi = wizard.get_by_role("button", name="Hindi · source", exact=True)
    expect(hindi).not_to_have_class("choice on")
    expect(hindi).to_be_disabled()
    wizard.get_by_role("button", name="Bengali", exact=True).click()
    expect(wizard.get_by_role("button", name="Bengali", exact=True)).to_have_class("choice on")
