"""Python Playwright journeys for the React screenplay workspace."""

import json
import re

from playwright.sync_api import Page, Route, expect


def test_project_opens_react_screenplay_workspace(page: Page) -> None:
    """Open a mocked project into the scene-aware React workspace."""
    project = {
        "id": 9001,
        "title": "The Lantern House",
        "logline": "A family returns to a house that remembers.",
        "description": "",
        "genres": ["Drama"],
        "languages": ["English"],
        "primary_language": "English",
        "artwork_url": None,
    }
    workspace = {
        "project": project,
        "screenplay": {"id": 12, "title": "The Lantern House", "format": "feature", "status": "draft"},
        "acts": [{"id": 4, "title": "Act One", "position": 0}],
        "scenes": [{"id": 7, "act_id": 4, "heading": "INT. LANTERN HOUSE - NIGHT", "position": 0, "body": "The house breathes in the dark."}],
        "blocks": {},
    }

    def projects(route: Route) -> None:
        """Return a project without contacting Postgres."""
        route.fulfill(status=200, content_type="application/json", body=json.dumps([project]))

    def workspace_request(route: Route) -> None:
        """Return a workspace without contacting Postgres."""
        route.fulfill(status=200, content_type="application/json", body=json.dumps(workspace))

    page.route("**/api/v1/projects", projects)
    page.route("**/api/v1/projects/9001/workspace", workspace_request)
    page.route("**/api/v1/projects/9001/agent-proposals", lambda route: route.fulfill(
        status=200, content_type="application/json", body="[]"
    ))
    page.goto("/projects")
    page.get_by_role("heading", name="The Lantern House").click()

    expect(page).to_have_url(re.compile(r"/projects/9001$"))
    expect(page.get_by_role("heading", name="The Lantern House")).to_be_visible()
    expect(page.get_by_role("article").get_by_text("INT. LANTERN HOUSE - NIGHT")).to_be_visible()
