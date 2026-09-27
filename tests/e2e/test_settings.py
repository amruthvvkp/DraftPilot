"""Python Playwright coverage for provider settings."""

import json

from playwright.sync_api import Page, Route, expect


def test_provider_settings_redacts_and_saves_credentials(page: Page) -> None:
    """Manage a provider profile through mocked server responses."""
    profile = {
        "id": 4,
        "name": "Studio Ollama",
        "provider": "ollama",
        "model": "llama3.2",
        "base_url": "http://ollama:11434/v1",
        "enabled": True,
        "has_api_key": True,
    }

    def handle(route: Route) -> None:
        """Return fixture profiles without contacting the backend database."""
        if route.request.method == "POST" or route.request.method == "PATCH":
            route.fulfill(status=200 if route.request.method == "PATCH" else 201, content_type="application/json", body=json.dumps(profile))
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps([profile]))

    page.route("**/api/v1/settings/providers**", handle)
    page.route(
        "**/api/v1/projects",
        lambda route: route.fulfill(status=200, content_type="application/json", body="[]"),
    )
    page.goto("/settings")
    expect(page.get_by_role("heading", name="Provider settings")).to_be_visible()
    expect(page.get_by_role("region", name="Copilot and agent proposals")).to_be_visible()
    expect(page.get_by_text("Credential stored securely")).to_be_visible()
    page.get_by_label("Profile name").fill("New local provider")
    page.get_by_label("API key").fill("never-render-this-secret")
    page.get_by_role("button", name="Save provider").click()
    expect(page.get_by_text("Credentials remain server-side.")).to_be_visible()
    expect(page.get_by_text("never-render-this-secret")).not_to_be_visible()


def test_writer_profile_persists_and_reflects_in_app_shell(page: Page) -> None:
    """Save the Writer twin to the server, add a memory, and see the pen name in the vault."""
    profile = {"name": "", "pen_name": "", "bio": "", "default_format": "feature", "default_language": "English", "style_notes": "", "preferences": {}, "updated_at": None}
    memories: list[dict[str, object]] = []
    saved: list[dict[str, object]] = []

    def profile_route(route: Route) -> None:
        """Serve and capture the server-side writer profile."""
        if route.request.method == "PUT":
            body = json.loads(route.request.post_data or "{}")
            saved.append(body)
            profile.update(body)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(profile))

    def memories_route(route: Route) -> None:
        """List and create writer memories."""
        if route.request.method == "POST":
            memory = {"id": len(memories) + 1, "created_at": "2026-09-27T10:00:00Z", "project_id": None, **json.loads(route.request.post_data or "{}")}
            memories.insert(0, memory)
            route.fulfill(status=201, content_type="application/json", body=json.dumps(memory))
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(memories))

    page.route("**/api/v1/writer/profile", profile_route)
    page.route("**/api/v1/writer/memories**", memories_route)
    page.route("**/api/v1/settings/providers**", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/projects", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.goto("/settings")
    expect(page.get_by_role("region", name="Writer Profile")).to_be_visible()
    page.get_by_label("Writer full name").fill("Maya Screenwriter")
    page.get_by_label("Writer pen name").fill("M. S. Writer")
    page.get_by_label("Writer style notes").fill("Lean action, wry dialogue.")
    page.get_by_role("button", name="Save writer profile").click()
    expect(page.get_by_text("Writer profile saved.")).to_be_visible()
    assert saved[-1]["pen_name"] == "M. S. Writer" and saved[-1]["style_notes"] == "Lean action, wry dialogue."
    memory_region = page.get_by_role("region", name="Writer memories")
    memory_region.get_by_label("Memory kind").select_option("taboo")
    memory_region.get_by_label("New memory").fill("Never kill the dog.")
    memory_region.get_by_role("button", name="Remember").click()
    expect(memory_region).to_contain_text("Never kill the dog.")
    assert memories[0]["kind"] == "taboo"
    page.goto("/projects")
    expect(page.locator(".user-profile-link")).to_contain_text("M. S. Writer")
