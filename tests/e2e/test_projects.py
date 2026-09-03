"""Python Playwright journeys for the React project studio."""

import json

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
    page.goto("/projects")
    page.get_by_role("button", name="New project").first.click()
    wizard = page.locator(".wizard")
    page.get_by_label("Project title").fill("Playwright story")
    page.get_by_role("button", name="Drama").click()
    wizard.get_by_role("button", name="Continue").click()
    expect(wizard.get_by_label("Description")).to_be_visible()
    wizard.get_by_role("button", name="Continue").click()
    expect(wizard.get_by_label("Creative references")).to_be_visible()
    wizard.get_by_role("button", name="Continue").click()
    expect(wizard.get_by_text("READY TO BEGIN")).to_be_visible()
    wizard.get_by_role("button", name="Create project", exact=False).click()
    expect(page.get_by_role("heading", name="Playwright story")).to_be_visible()
