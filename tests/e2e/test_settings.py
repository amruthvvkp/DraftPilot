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
    """Persist writer profile locally and verify presence across navigation."""
    page.route("**/api/v1/settings/providers", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/projects", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.goto("/settings")
    expect(page.get_by_role("region", name="Writer Profile")).to_be_visible()
    page.get_by_label("Writer full name").fill("Maya Screenwriter")
    page.get_by_label("Writer pen name").fill("M. S. Writer")
    page.get_by_role("button", name="Save writer profile").click()
    expect(page.get_by_text("Profile saved locally.")).to_be_visible()
    page.goto("/projects")
    expect(page.locator(".user-profile-link")).to_contain_text("M. S. Writer")

