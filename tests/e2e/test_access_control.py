"""Python Playwright journeys for API sign-in and writer approval of external agents."""

import json

from playwright.sync_api import Page, Route, expect

PROJECT = {
    "id": 9001,
    "title": "The Lantern House",
    "logline": "A family returns to a house that remembers.",
    "description": "",
    "genres": ["Drama"],
    "languages": ["English"],
    "primary_language": "English",
    "artwork_url": None,
    "project_instruction": "",
    "version": 1,
}


def _json(route: Route, body: object, status: int = 200) -> None:
    """Fulfil a mocked API route with a JSON body."""
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


def test_token_protected_studio_asks_for_sign_in(page: Page) -> None:
    """A configured API token shows a sign-in form and unlocks the vault once accepted."""
    state = {"authenticated": False}
    submitted: list[str] = []

    def status(route: Route) -> None:
        """Report the mocked authentication state."""
        _json(route, {"auth_required": True, "authenticated": state["authenticated"]})

    def session(route: Route) -> None:
        """Accept only the correct token and start a session."""
        token = json.loads(route.request.post_data or "{}").get("token", "")
        submitted.append(token)
        if token != "right-token":
            _json(route, {"detail": "Invalid API token"}, 401)
            return
        state["authenticated"] = True
        _json(route, {"auth_required": True, "authenticated": True})

    page.route("**/api/v1/auth/status", status)
    page.route("**/api/v1/auth/session", session)
    page.route("**/api/v1/projects", lambda route: _json(route, [PROJECT]))
    page.goto("/projects")
    expect(page.get_by_role("heading", name="Sign in to DraftPilot")).to_be_visible()
    page.get_by_label("API token").fill("wrong-token")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("alert")).to_contain_text("not accepted")
    page.get_by_label("API token").fill("right-token")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("The Lantern House").first).to_be_visible()
    assert submitted == ["wrong-token", "right-token"]


def test_writer_decides_external_agent_requests_in_the_workspace(page: Page) -> None:
    """Pending MCP approval requests appear in the workspace and the writer decides them."""
    workspace = {
        "project": PROJECT,
        "screenplay": {"id": 12, "title": "The Lantern House", "format": "feature", "status": "draft"},
        "acts": [{"id": 4, "title": "Act One", "position": 0}],
        "scenes": [{"id": 7, "act_id": 4, "heading": "INT. LANTERN HOUSE - NIGHT", "position": 0, "body": "", "version": 2}],
        "blocks": {"7": []},
    }
    approval = {
        "id": 31,
        "client_id": "claude-code",
        "project_id": 9001,
        "capability": "story.operation",
        "action": "apply",
        "summary": {"artifact_id": 3, "operation": "set_logline", "payload": {"logline": "A house remembers."}},
        "status": "pending",
        "created_at": "2026-09-27T09:00:00Z",
        "expires_at": "2099-09-27T09:15:00Z",
        "decided_at": None,
    }
    decisions: list[str] = []

    def approvals(route: Route) -> None:
        """List the pending request until the writer decides it."""
        _json(route, [] if decisions else [approval])

    def decide(route: Route) -> None:
        """Record the writer's decision."""
        decisions.append(route.request.url.rsplit("/", 1)[-1])
        _json(route, {**approval, "status": "approved"})

    page.route("**/api/v1/projects", lambda route: _json(route, [PROJECT]))
    page.route("**/api/v1/projects/9001/workspace", lambda route: _json(route, workspace))
    page.route("**/api/v1/projects/9001/mcp-approvals?state=pending", approvals)
    page.route("**/api/v1/projects/9001/mcp-approvals/31/*", decide)
    for path in ["agent-proposals", "evaluations", "copilot/messages", "backups", "scenes/7/revisions", "screenplays/12/timeline/proposals"]:
        page.route(f"**/api/v1/projects/9001/{path}", lambda route: _json(route, []))
    page.route("**/api/v1/agents/roles", lambda route: _json(route, []))
    page.route("**/api/v1/settings/providers", lambda route: _json(route, []))
    page.route("**/api/v1/capabilities**", lambda route: _json(route, []))
    page.goto("/projects/9001")
    requests = page.get_by_role("region", name="External agent approvals")
    expect(requests).to_contain_text("claude-code")
    expect(requests).to_contain_text("A house remembers.")
    requests.get_by_role("button", name="Approve request").click()
    expect(requests).not_to_be_visible()
    assert decisions == ["approve"]
