"""Python Playwright journey for the writers' room: launch a workflow, watch it, review its proposals."""

import json

from playwright.sync_api import Page, Route, expect

PROJECT = {"id": 9002, "title": "Big Fish", "logline": "", "description": "", "genres": [], "languages": ["English"], "primary_language": "English", "artwork_url": None}
WORKSPACE = {
    "project": PROJECT,
    "screenplay": {"id": 3, "title": "Big Fish", "format": "feature", "status": "draft"},
    "screenplays": [],
    "acts": [{"id": 1, "title": None, "position": 0}],
    "scenes": [
        {"id": 11, "act_id": 1, "heading": "EXT. RIVER - DAY", "position": 0, "body": "", "version": 1},
        {"id": 12, "act_id": 1, "heading": "INT. WILL'S BEDROOM - NIGHT", "position": 1, "body": "", "version": 3},
    ],
    "blocks": {},
}
WORKFLOWS = [
    {
        "key": "rewrite_scene",
        "label": "Rewrite a scene",
        "description": "Rewrite one scene to your brief through a draft-critique loop.",
        "roles": ["scene_writer", "script_doctor"],
        "proposes": True,
        "params_schema": {
            "type": "object",
            "required": ["scene_id", "brief"],
            "properties": {
                "scene_id": {"type": "integer", "title": "Scene Id"},
                "brief": {"type": "string", "title": "Brief", "maxLength": 4000},
                "max_rounds": {"type": "integer", "title": "Max Rounds", "default": 2, "minimum": 0, "maximum": 4},
                "target_score": {"type": "integer", "title": "Target Score", "default": 8, "minimum": 1, "maximum": 10},
            },
        },
    },
    {
        "key": "coverage",
        "label": "Coverage",
        "description": "Studio-style coverage with graded craft and a verdict.",
        "roles": ["coverage_reader"],
        "proposes": False,
        "params_schema": {"type": "object", "properties": {"focus": {"type": "string", "title": "Focus", "default": "", "maxLength": 2000}}},
    },
]


def test_writer_launches_a_rewrite_and_approves_its_proposal(page: Page) -> None:
    """The launcher builds its form from the schema; a finished run shows its trail, result and proposal."""
    started: list[dict[str, object]] = []
    runs: list[dict[str, object]] = []
    approved: list[str] = []
    proposal = {
        "id": 71, "project_id": 9002, "run_id": 501, "target_kind": "scene", "target_id": 12, "operation": {}, "before": {},
        "diff": {"summary": "Rewrite: Shorter, with subtext"}, "base_version": 3, "status": "proposed",
    }

    def start(route: Route) -> None:
        """Record the start request and return a finished run (the worker is mocked away)."""
        if route.request.method == "GET":
            route.fulfill(status=200, content_type="application/json", body=json.dumps(WORKFLOWS))
            return
        started.append(route.request.post_data_json)
        run = {
            "id": 501, "project_id": 9002, "kind": "room_workflow", "status": "succeeded", "attempt_count": 1, "max_attempts": 1, "error": None,
            "input": {"workflow": "rewrite_scene"}, "created_at": "2026-09-27T10:00:00Z",
            "result": {
                "workflow": "rewrite_scene", "fountain": "INT. WILL'S BEDROOM - NIGHT\n\nWill stares at the ceiling.", "rationale": "Less said.",
                "critique": {"score": 9}, "rounds": 0, "proposal_ids": [71], "checks": {"valid_scene": 1.0, "critique_score": 0.9},
                "trail": [
                    {"step": "draft", "role": "scene_writer", "duration_ms": 41000, "output": {}},
                    {"step": "critique_1", "role": "script_doctor", "duration_ms": 12000, "output": {}},
                ],
            },
        }
        runs.insert(0, run)
        route.fulfill(status=202, content_type="application/json", body=json.dumps(run))

    def approve(route: Route) -> None:
        """Approve the proposal."""
        approved.append(route.request.url)
        proposal["status"] = "approved"
        route.fulfill(status=200, content_type="application/json", body=json.dumps(proposal))

    page.route("**/api/v1/projects/9002/room/workflows", start)
    page.route("**/api/v1/projects/9002/workspace**", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(WORKSPACE)))
    page.route("**/api/v1/projects/9002/runs", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(runs)))
    page.route("**/api/v1/projects/9002/agent-proposals", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps([proposal] if runs else [])))
    page.route("**/api/v1/projects/9002/agent-proposals/71/approve", approve)
    page.route("**/api/v1/projects/9002/events", lambda route: route.fulfill(status=204, body=""))
    feedback: list[dict[str, object]] = []

    def give_feedback(route: Route) -> None:
        """Record the thumbs."""
        feedback.append(route.request.post_data_json)
        route.fulfill(status=201, content_type="application/json", body="{}")

    insights = {"workflows": {}, "roles": {}}

    def get_insights(route: Route) -> None:
        """Report usefulness once the rewrite has been decided."""
        if proposal["status"] == "approved":
            insights["workflows"] = {"rewrite_scene": {"runs": 1, "succeeded": 1, "failed": 0, "approved": 1, "rejected": 0, "rolled_back": 0, "pending": 0, "up": len(feedback), "down": 0,
                                                       "acceptance": 1.0, "retention": 0.8, "thumbs_up_share": 1.0 if feedback else None, "usefulness": 0.93, "mean_duration_s": 53.0}}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(insights))

    page.route("**/api/v1/projects/9002/feedback", give_feedback)
    page.route("**/api/v1/projects/9002/insights", get_insights)

    page.goto("/projects/9002/room")
    expect(page.get_by_role("heading", name="Put the room to work")).to_be_visible()
    expect(page.get_by_text("With Scene writer · Script doctor")).to_be_visible()
    start_button = page.get_by_role("button", name="Start rewrite a scene")
    expect(start_button).to_be_disabled()  # scene and brief are required

    page.get_by_label("Scene Id").select_option(label="2. INT. WILL'S BEDROOM - NIGHT")
    page.get_by_label("Brief").fill("Shorter, with subtext")
    expect(page.get_by_label("Max Rounds")).to_have_value("2")
    start_button.click()

    expect(page.get_by_text("Will stares at the ceiling.")).to_be_visible()
    assert started == [{"workflow": "rewrite_scene", "params": {"scene_id": 12, "brief": "Shorter, with subtext", "max_rounds": 2, "target_score": 8}, "provider_profile_id": None}]
    expect(page.get_by_text("Script doctor: 9/10")).to_be_visible()
    expect(page.locator(".room-trail li")).to_have_count(2)
    expect(page.get_by_text("Rewrite: Shorter, with subtext")).to_be_visible()
    page.get_by_role("button", name="Approve").click()
    expect(page.get_by_role("button", name="Roll back")).to_be_visible()
    assert len(approved) == 1
    expect(page.get_by_text("valid scene ✓")).to_be_visible()
    page.get_by_role("button", name="Helpful", exact=True).click()
    expect(page.get_by_role("button", name="Helpful", exact=True)).to_have_attribute("aria-pressed", "true")
    assert feedback == [{"workflow_run_id": 501, "rating": 1, "comment": ""}]
    insights_table = page.get_by_label("Room usefulness")
    expect(insights_table.get_by_role("cell", name="Rewrite a scene")).to_be_visible()
    expect(insights_table.get_by_text("93%")).to_be_visible()

    page.get_by_role("tab", name="Coverage").click()
    expect(page.get_by_role("button", name="Start coverage")).to_be_enabled()
    expect(page.get_by_text("Report", exact=True).first).to_be_visible()
