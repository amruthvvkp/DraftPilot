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
    page.get_by_role("button", name="Drama", exact=True).click()
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
    expect(wizard.get_by_role("button", name="Film Noir", exact=True)).to_be_visible()
    expect(wizard.get_by_role("button", name="Psychological", exact=True)).to_be_visible()
    wizard.get_by_role("button", name="Continue").click()
    primary = wizard.get_by_label("Primary screenplay language")
    primary.select_option(label="Hindi")
    hindi = wizard.get_by_role("button", name="Hindi · source", exact=True)
    expect(hindi).not_to_have_class("choice on")
    expect(hindi).to_be_disabled()
    wizard.get_by_role("button", name="Bengali", exact=True).click()
    expect(wizard.get_by_role("button", name="Bengali", exact=True)).to_have_class("choice on")


def test_wizard_ai_assist_populates_story_structure(page: Page) -> None:
    """Populate project creation wizard fields using the AI assist trigger."""
    mock_projects_api(page)
    page.route(
        "**/api/v1/projects/wizard/assist",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "title": "The Quantum Lighthouse",
                "logline": "A solitary keeper intercepts future broadcasts.",
                "description": "An exploration of time and guilt.",
                "story_outline": "Act I: Signals arrive.\nAct II: The timeline bends.\nAct III: The light fails.",
                "genres": ["Sci-Fi", "Mystery"],
                "target_audience": "Cinematic sci-fi audience",
                "characters": [{"name": "Elias", "role": "lead", "description": "Lighthouse keeper"}],
                "visual_style": "High-contrast coastal chiaroscuro",
                "camera_type": "Digital",
                "screening_type": "flat_1_85",
                "primary_language": "English",
                "format": "feature",
            }),
        ),
    )
    page.goto("/projects")
    page.get_by_role("button", name="New project").first.click()
    expect(page.get_by_label("AI Story Assistant")).to_be_visible()
    spark_input = page.get_by_label("Story premise spark")
    spark_input.fill("A lighthouse keeper discovers radio signals from the future")
    page.get_by_role("button", name="Spark story ✦").click()
    expect(page.get_by_label("Project title")).to_have_value("The Quantum Lighthouse")
    expect(page.get_by_label("Logline")).to_have_value("A solitary keeper intercepts future broadcasts.")
    expect(page.get_by_role("button", name="Sci-Fi", exact=True)).to_have_class("choice on")



def test_vault_duplicates_deletes_with_confirmation_and_restores(page: Page) -> None:
    """Duplicate from the card menu; delete only after typing the title; restore from Recently deleted."""
    projects = [{"id": 11, "title": "Big Fish", "logline": "Tall tales.", "description": "", "genres": [], "languages": ["English"], "artwork_url": None}]
    deleted: list[dict[str, object]] = []
    calls: list[str] = []

    def listing(route: Route) -> None:
        """Serve the current project list."""
        route.fulfill(status=200, content_type="application/json", body=json.dumps(projects))

    def duplicate(route: Route) -> None:
        """Copy the project."""
        calls.append("duplicate")
        copy = {**projects[0], "id": 12, "title": "Big Fish (copy)"}
        projects.append(copy)
        route.fulfill(status=201, content_type="application/json", body=json.dumps(copy))

    def remove(route: Route) -> None:
        """Delete the copy, keeping a backup."""
        calls.append(f"{route.request.method} {route.request.url.rsplit('/', 1)[-1]}")
        projects.pop()
        deleted.append({"project_id": 12, "title": "Big Fish (copy)", "filename": "Big-Fish-copy-deleted-12.json.gz", "deleted_at": "2026-09-27T12:00:00+00:00"})
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"project_id": 12, "title": "Big Fish (copy)", "backup": "x", "removed": {}}))

    def restore(route: Route) -> None:
        """Restore the deleted copy."""
        calls.append("restore")
        deleted.clear()
        projects.append({**projects[0], "id": 13, "title": "Big Fish (copy)"})
        route.fulfill(status=201, content_type="application/json", body=json.dumps({"project_id": 13}))

    page.route("**/api/v1/projects", listing)
    page.route("**/api/v1/projects/deleted", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(deleted)))
    page.route("**/api/v1/projects/11/duplicate", duplicate)
    page.route("**/api/v1/projects/12", remove)
    page.route("**/api/v1/projects/12/backups/*/restore", restore)
    page.route("**/api/v1/writer/profile", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"name": "", "pen_name": "", "preferences": {}})))

    page.goto("/projects")
    page.get_by_role("button", name="Actions for Big Fish").click()
    page.get_by_role("menuitem", name="Duplicate").click()
    expect(page.get_by_text("Duplicated as “Big Fish (copy)”.")).to_be_visible()

    page.get_by_role("button", name="Actions for Big Fish (copy)").click()
    page.get_by_role("menuitem", name="Delete…").click()
    dialog = page.get_by_role("dialog", name="Delete Big Fish (copy)")
    confirm = dialog.get_by_role("button", name="Delete project")
    expect(confirm).to_be_disabled()
    dialog.get_by_label("Project title to confirm").fill("Big Fish")
    expect(confirm).to_be_disabled()
    dialog.get_by_label("Project title to confirm").fill("Big Fish (copy)")
    confirm.click()
    expect(page.get_by_text("A backup was kept")).to_be_visible()
    recovery = page.get_by_role("region", name="Recently deleted")
    expect(recovery.get_by_text("Big Fish (copy)")).to_be_visible()
    recovery.get_by_role("button", name="Restore").click()
    expect(page.get_by_text("Restored “Big Fish (copy)”.")).to_be_visible()
    expect(page.get_by_role("region", name="Recently deleted")).to_have_count(0)
    assert calls == ["duplicate", "DELETE 12", "restore"]
