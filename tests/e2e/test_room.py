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
    runs_region = page.get_by_role("region", name="Room runs")
    runs_region.get_by_role("button", name="Approve").click()
    expect(runs_region.get_by_role("button", name="Roll back")).to_be_visible()
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


def _stream(*events: dict[str, object]) -> str:
    """Encode AG-UI events as server-sent events."""
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events)


def _reply(run_id: str, text: str) -> list[dict[str, object]]:
    """Return the events of a turn that only says ``text``."""
    return [
        {"type": "RUN_STARTED", "threadId": "t", "runId": run_id},
        {"type": "TEXT_MESSAGE_START", "messageId": f"m-{run_id}", "role": "assistant"},
        {"type": "TEXT_MESSAGE_CONTENT", "messageId": f"m-{run_id}", "delta": text},
        {"type": "TEXT_MESSAGE_END", "messageId": f"m-{run_id}"},
        {"type": "RUN_FINISHED", "threadId": "t", "runId": run_id, "outcome": {"type": "success"}},
    ]


def _room_routes(page: Page, chat: object) -> None:
    """Mock the room page and its chat endpoint."""
    page.route("**/api/v1/projects/9002/room/chat", chat)  # type: ignore[arg-type]
    page.route("**/api/v1/projects/9002/room/workflows", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(WORKFLOWS)))
    page.route("**/api/v1/projects/9002/room/threads", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/projects/9002/room/threads/*", lambda route: route.fulfill(status=404, content_type="application/json", body='{"detail": "Thread not found"}'))
    page.route("**/api/v1/projects/9002/workspace**", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(WORKSPACE)))
    for path in ("runs", "agent-proposals", "characters", "beats"):
        page.route(f"**/api/v1/projects/9002/{path}", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/projects/9002/insights", lambda route: route.fulfill(status=200, content_type="application/json", body='{"workflows":{},"roles":{}}'))
    page.route("**/api/v1/projects/9002/events", lambda route: route.fulfill(status=204, body=""))
    page.route("**/api/v1/settings/providers", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/agents/roles", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps([
        {"key": "showrunner", "label": "Showrunner", "description": "", "default_permission": "chat_only"},
        {"key": "script_editor", "label": "Script editor", "description": "", "default_permission": "chat_only"},
    ])))


def test_room_chat_streams_the_answer_and_shows_the_tools_used(page: Page) -> None:
    """The dock streams the showrunner's AG-UI reply, with tool cards; role, mode and page ride in forwardedProps."""
    bodies: list[dict[str, object]] = []

    def chat(route: Route) -> None:
        """Answer the first turn with a tool call, a delegated consult and streamed Markdown; then a plain reply."""
        bodies.append(route.request.post_data_json)
        if len(bodies) == 1:
            events = [
                {"type": "RUN_STARTED", "threadId": "t", "runId": "r1"},
                {"type": "TOOL_CALL_START", "toolCallId": "c1", "toolCallName": "read_story_twin", "parentMessageId": "a1"},
                {"type": "TOOL_CALL_ARGS", "toolCallId": "c1", "delta": json.dumps({"project_id": 9002})},
                {"type": "TOOL_CALL_END", "toolCallId": "c1"},
                {"type": "TOOL_CALL_RESULT", "toolCallId": "c1", "messageId": "x1", "content": json.dumps({"characters": []})},
                {"type": "TOOL_CALL_START", "toolCallId": "c2", "toolCallName": "consult", "parentMessageId": "a1"},
                {"type": "TOOL_CALL_ARGS", "toolCallId": "c2", "delta": json.dumps({"role": "character_specialist", "brief": "Will's want"})},
                {"type": "TOOL_CALL_END", "toolCallId": "c2"},
                {"type": "TOOL_CALL_RESULT", "toolCallId": "c2", "messageId": "x2", "content": "[Character specialist] He wants the truth."},
                {"type": "TEXT_MESSAGE_START", "messageId": "m1", "role": "assistant"},
                {"type": "TEXT_MESSAGE_CONTENT", "messageId": "m1", "delta": "Will wants his father "},
                {"type": "TEXT_MESSAGE_CONTENT", "messageId": "m1", "delta": "to be **real**."},
                {"type": "TEXT_MESSAGE_END", "messageId": "m1"},
                {"type": "RUN_FINISHED", "threadId": "t", "runId": "r1", "outcome": {"type": "success"}},
            ]
        else:
            events = _reply("r2", "Scene 2, tightened.")
        route.fulfill(status=200, headers={"content-type": "text/event-stream"}, body=_stream(*events))

    _room_routes(page, chat)
    page.set_viewport_size({"width": 1500, "height": 900})  # wide enough for the chat dock to start open
    page.goto("/projects/9002/room")
    dock = page.get_by_role("complementary", name="Chat")
    dock.get_by_label("Message the room").fill("What does Will want from Edward?")
    dock.get_by_role("button", name="Send").click()
    expect(dock.get_by_text("Will wants his father to be real.")).to_be_visible()
    expect(dock.locator("strong", has_text="real")).to_be_visible()
    expect(dock.get_by_text("Checked the Story twin ✓")).to_be_visible()
    expect(dock.get_by_text("Character specialist ✓")).to_be_visible()
    first = bodies[0]
    assert first["forwardedProps"]["role"] == "showrunner" and first["forwardedProps"]["permission_mode"] == "suggest"  # type: ignore[index]
    assert first["forwardedProps"]["page"] == "/projects/9002/room"  # type: ignore[index]
    assert first["messages"][-1]["content"] == "What does Will want from Edward?"  # type: ignore[index]

    dock.get_by_label("Room role").select_option("script_editor")
    dock.get_by_label("Chat permission").select_option("chat_only")
    dock.get_by_label("Message the room").fill("Tighten scene 2.")
    dock.get_by_label("Message the room").press("Enter")
    expect(dock.get_by_text("Scene 2, tightened.")).to_be_visible()
    assert bodies[1]["threadId"] == first["threadId"]
    assert bodies[1]["forwardedProps"]["role"] == "script_editor" and bodies[1]["forwardedProps"]["permission_mode"] == "chat_only"  # type: ignore[index]

    # The dock is the same on every project page, and keeps the conversation.
    page.get_by_role("navigation", name="Project steps").get_by_role("link", name="Outline").click()
    expect(dock.get_by_text("Scene 2, tightened.")).to_be_visible()


def test_chat_approval_card_runs_the_write_after_approval(page: Page) -> None:
    """In "Edit with approval" mode a write ends the turn with an interrupt; approving resumes it and shows the result."""
    bodies: list[dict[str, object]] = []
    karl = {"project_id": 9002, "kind": "character", "fields": {"name": "Karl", "role": "supporting"}}

    def chat(route: Route) -> None:
        """Interrupt on the write, then run it once the writer approves."""
        bodies.append(route.request.post_data_json)
        if len(bodies) == 1:
            events = [
                {"type": "RUN_STARTED", "threadId": "t", "runId": "r1"},
                {"type": "TOOL_CALL_START", "toolCallId": "c1", "toolCallName": "create_story_entity", "parentMessageId": "a1"},
                {"type": "TOOL_CALL_ARGS", "toolCallId": "c1", "delta": json.dumps(karl)},
                {"type": "TOOL_CALL_END", "toolCallId": "c1"},
                {"type": "RUN_FINISHED", "threadId": "t", "runId": "r1", "outcome": {"type": "interrupt", "interrupts": [
                    {"id": "int-c1", "reason": "tool_call", "message": "Approve create_story_entity?", "toolCallId": "c1",
                     "responseSchema": {"type": "object", "properties": {"approved": {"type": "boolean"}}, "required": ["approved"]}},
                ]}},
            ]
        else:
            created = {"id": 31, "project_id": 9002, "name": "Karl", "role": "supporting", "want": "To be seen", "source": "agent", "version": 1}
            events = [
                {"type": "RUN_STARTED", "threadId": "t", "runId": "r2"},
                {"type": "TOOL_CALL_RESULT", "toolCallId": "c1", "messageId": "x1", "content": json.dumps(created)},
                *_reply("r2", "Karl the giant is in the cast.")[1:],
            ]
        route.fulfill(status=200, headers={"content-type": "text/event-stream"}, body=_stream(*events))

    _room_routes(page, chat)
    page.set_viewport_size({"width": 1500, "height": 900})  # wide enough for the chat dock to start open
    page.goto("/projects/9002/room")
    dock = page.get_by_role("complementary", name="Chat")
    dock.get_by_label("Chat permission").select_option(label="Edit with approval")
    dock.get_by_label("Message the room").fill("Add Karl the giant.")
    dock.get_by_role("button", name="Send").click()
    card = dock.get_by_role("region", name="Approve create_story_entity")
    expect(card).to_contain_text("Needs your approval")
    expect(card).to_contain_text('"name": "Karl"')
    card.get_by_role("button", name="Approve", exact=True).click()
    expect(dock.get_by_text("Karl the giant is in the cast.")).to_be_visible()
    expect(dock.get_by_text("New character: Karl")).to_be_visible()
    expect(dock.get_by_role("link", name="Open Karl ↗")).to_have_attribute("href", "/projects/9002/characters/31")
    assert bodies[0]["forwardedProps"]["permission_mode"] == "project_edit"  # type: ignore[index]
    assert bodies[1]["threadId"] == bodies[0]["threadId"] and bodies[1]["messages"] == []
    assert bodies[1]["resume"] == [{"interruptId": "int-c1", "status": "resolved", "payload": {"approved": True}}]
