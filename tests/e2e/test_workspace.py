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
        "languages": ["English", "Hindi"],
        "primary_language": "English",
        "artwork_url": None,
    }
    workspace = {
        "project": project,
        "screenplay": {"id": 12, "title": "The Lantern House", "format": "feature", "status": "draft"},
        "acts": [{"id": 4, "title": "Act One", "position": 0}],
        "scenes": [{"id": 7, "act_id": 4, "heading": "INT. LANTERN HOUSE - NIGHT", "position": 0, "body": "The house breathes in the dark.", "version": 2}],
        "blocks": {"7": [{"id": 20, "scene_id": 7, "position": 0, "element_type": "action", "text": "The house breathes in the dark.", "character_extension": None, "is_dual": False, "dual_group": None, "translation": None, "translation_lang": None}, {"id": 21, "scene_id": 7, "position": 1, "element_type": "dialogue", "text": "We should go.", "character_extension": None, "is_dual": True, "dual_group": 3, "translation": None, "translation_lang": None}]},
    }

    def projects(route: Route) -> None:
        """Return a project without contacting Postgres."""
        route.fulfill(status=200, content_type="application/json", body=json.dumps([project]))

    def workspace_request(route: Route) -> None:
        """Return a workspace without contacting Postgres."""
        route.fulfill(status=200, content_type="application/json", body=json.dumps(workspace))

    def block_update(route: Route) -> None:
        """Accept a versioned semantic block edit without contacting Postgres."""
        assert route.request.headers.get("if-match") == "2"
        route.fulfill(status=200, content_type="application/json", body=json.dumps(workspace["blocks"]["7"][0]))

    page.route("**/api/v1/projects", projects)
    page.route("**/api/v1/projects/9001/workspace", workspace_request)
    page.route("**/api/v1/projects/9001/scenes/7/blocks/*", block_update)
    page.route("**/api/v1/projects/9001/agent-proposals", lambda route: route.fulfill(
        status=200, content_type="application/json", body="[]"
    ))
    page.route("**/api/v1/projects/9001/copilot/messages", lambda route: route.fulfill(
        status=200, content_type="application/json", body="[]"
    ))
    page.route("**/api/v1/agents/roles", lambda route: route.fulfill(
        status=200, content_type="application/json", body='[{"key":"story_architect","label":"Story architect","description":"Shape the story.","default_permission":"chat_only"}]'
    ))
    page.route("**/api/v1/settings/providers", lambda route: route.fulfill(
        status=200, content_type="application/json", body="[]"
    ))
    page.goto("/projects")
    page.get_by_role("heading", name="The Lantern House").click()

    expect(page).to_have_url(re.compile(r"/projects/9001$"))
    expect(page.get_by_role("heading", name="The Lantern House")).to_be_visible()
    expect(page.get_by_label("Edit scene heading")).to_have_value("INT. LANTERN HOUSE - NIGHT")
    editor = page.get_by_label("Edit action")
    expect(editor).to_have_value("The house breathes in the dark.")
    editor.fill("The house exhales in the dark.")
    editor.press("Tab")
    expect(page.get_by_label("Edit dialogue")).to_be_focused()
    editor.blur()


def test_story_artifact_workspace_is_editable(page: Page) -> None:
    """Edit a persisted story artifact through the project-scoped studio."""
    artifact = {"id": 31, "project_id": 9001, "kind": "brief", "title": "First pass", "content": "A family returns.", "version": 2, "stale": True, "depends_on": [], "artifact_metadata": {}}
    page.route("**/api/v1/projects/9001/artifacts", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps([artifact])))
    page.route("**/api/v1/projects/9001/agent-proposals", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/projects/9001/copilot/messages", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/agents/roles", lambda route: route.fulfill(status=200, content_type="application/json", body='[{"key":"story_architect","label":"Story architect","description":"Shape the story.","default_permission":"chat_only"}]'))
    page.route("**/api/v1/settings/providers", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/projects/9001/artifacts/31", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(artifact)))
    page.goto("/projects/9001/studio")
    expect(page.get_by_role("heading", name="Creative artifacts")).to_be_visible()
    expect(page.get_by_role("button", name="brief First pass STALE")).to_be_visible()
    content = page.get_by_label("Artifact content")
    content.fill("A family returns to a house that remembers.")
    content.blur()


def test_copilot_turn_polls_durable_run(page: Page) -> None:
    """Submit a Copilot turn and reload its persisted assistant response."""
    artifact = {"id": 31, "project_id": 9001, "kind": "brief", "title": "First pass", "content": "A family returns.", "version": 2, "stale": False, "depends_on": [], "artifact_metadata": {}}
    assistant = {"id": 32, "project_id": 9001, "role": "assistant", "content": "The reveal needs a setup.", "page": "studio", "artifact": None, "selection": None, "instruction_layers": {}, "citations": [], "active_tools": [], "created_at": "2026-01-01T00:00:00Z"}
    message_reads = 0

    page.route("**/api/v1/projects/9001/artifacts", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps([artifact])))
    page.route("**/api/v1/projects/9001/artifacts/31", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(artifact)))
    page.route("**/api/v1/projects/9001/agent-proposals", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/agents/roles", lambda route: route.fulfill(status=200, content_type="application/json", body='[{"key":"story_architect","label":"Story architect","description":"Shape the story.","default_permission":"chat_only"}]'))
    page.route("**/api/v1/settings/providers", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))

    def messages(route: Route) -> None:
        """Return the assistant only after the durable run completes."""
        nonlocal message_reads
        message_reads += 1
        route.fulfill(status=200, content_type="application/json", body=json.dumps([assistant] if message_reads > 1 else []))

    page.route("**/api/v1/projects/9001/copilot/messages", messages)
    page.route("**/api/v1/projects/9001/copilot/messages/respond-async", lambda route: route.fulfill(status=202, content_type="application/json", body=json.dumps({"message": {"id": 30, "project_id": 9001, "role": "user", "content": "Find the gap.", "page": "studio", "artifact": None, "selection": None, "instruction_layers": {"agent_role": "story_architect", "permission_mode": "chat_only", "provider_profile_id": None}, "citations": [], "active_tools": [], "created_at": "2026-01-01T00:00:00Z"}, "run": {"id": 44, "project_id": 9001, "kind": "copilot_response", "status": "queued", "result": None, "error": None}})))
    page.route("**/api/v1/projects/9001/runs/44", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"id": 44, "project_id": 9001, "kind": "copilot_response", "status": "succeeded", "result": {"assistant_message_id": 32}, "error": None})))
    page.goto("/projects/9001/studio")
    page.get_by_label("Copilot message").fill("Find the gap.")
    page.get_by_role("button", name="Send").click()
    expect(page.get_by_text("The reveal needs a setup.")).to_be_visible()
