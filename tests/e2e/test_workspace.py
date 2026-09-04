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
        "blocks": {"7": [{"id": 20, "scene_id": 7, "position": 0, "element_type": "action", "text": "The house breathes in the dark.", "character_extension": None, "is_dual": False, "dual_group": None, "translation": None, "translation_lang": None}, {"id": 21, "scene_id": 7, "position": 1, "element_type": "dialogue", "text": "We should go.", "character_extension": None, "is_dual": True, "dual_group": 3, "translation": None, "translation_lang": None}, {"id": 22, "scene_id": 7, "position": 2, "element_type": "character", "text": "MIRA", "character_extension": None, "is_dual": False, "dual_group": None, "translation": None, "translation_lang": None}]},
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
    page.route("**/api/v1/projects/9001/scenes/7/revisions", lambda route: route.fulfill(
        status=200, content_type="application/json", body='[{"id":30,"scene_id":7,"rev_number":1,"message":"Opening","created_at":"2026-01-01T00:00:00Z"}]'
    ))

    def restore_revision(route: Route) -> None:
        """Validate selective scene-section restoration."""
        assert route.request.post_data_json == {"sections": ["blocks"]}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(workspace["scenes"][0]))

    page.route("**/api/v1/projects/9001/scenes/7/revisions/30/restore", restore_revision)
    proposals: list[dict[str, object]] = []

    def agent_proposals(route: Route) -> None:
        """Persist a typed formatting proposal in the browser fixture."""
        if route.request.method == "POST":
            payload = route.request.post_data_json
            assert payload["target_kind"] == "block"
            assert payload["target_id"] == 20
            assert payload["operation"] == {"element_type": "dialogue"}
            proposal = {"id": 80, "project_id": 9001, "run_id": None, "target_kind": "block", "target_id": 20, "operation": payload["operation"], "diff": payload["diff"], "before": {"scene_id": 7, "element_type": "action"}, "base_version": 2, "status": "proposed"}
            proposals.append(proposal)
            route.fulfill(status=201, content_type="application/json", body=json.dumps(proposal))
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(proposals))

    backup = {"filename": "9001-20260101T000000Z.json.gz", "manifest": {"schema_version": 1, "project_id": 9001, "created_at": "2026-01-01T00:00:00Z", "app_version": "0.1.0", "sha256": "abcdef1234567890"}}
    page.route("**/api/v1/projects/9001/backups", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps([backup])))
    page.route("**/api/v1/projects/9001/agent-proposals", agent_proposals)
    page.route("**/api/v1/projects/9001/evaluations", lambda route: route.fulfill(
        status=200, content_type="application/json", body="[]"
    ))
    page.route("**/api/v1/projects/9001/screenplays/12/timeline/proposals", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps([{"id": 60, "project_id": 9001, "screenplay_id": 12, "status": "proposed", "original_scene_ids": [7], "proposed_scene_ids": [7], "timings": [{"scene_id": 7, "position": 0, "start_seconds": 0, "end_seconds": 30}], "total_runtime_seconds": 30}])
    ))

    def start_review(route: Route) -> None:
        """Validate the screenplay-scoped evaluation run request."""
        assert route.request.post_data_json == {"screenplay_id": 12, "evaluator": "deterministic_review"}
        route.fulfill(status=202, content_type="application/json", body=json.dumps({"id": 55, "project_id": 9001, "kind": "evaluation", "status": "queued", "result": None, "error": None}))

    page.route("**/api/v1/projects/9001/evaluations/runs", start_review)
    page.route("**/api/v1/projects/9001/runs/55", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"id": 55, "project_id": 9001, "kind": "evaluation", "status": "succeeded", "result": {"evaluation_id": 3}, "error": None})))
    page.route("**/api/v1/projects/9001/copilot/messages", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps([{"id": 32, "project_id": 9001, "role": "assistant", "content": "The reveal needs a setup.", "page": "workspace", "artifact": "screenplay", "selection": "INT. LANTERN HOUSE - NIGHT", "instruction_layers": {}, "citations": [{"source_id": "artifact:3", "content_version": 2}], "active_tools": ["screenplay.read"], "created_at": "2026-01-01T00:00:00Z"}])
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
    expect(page.get_by_role("button", name="Unpair")).to_be_visible()
    expect(page.get_by_label("New scene heading")).to_have_value("INT. - DAY")
    expect(page.get_by_label("New screenplay element")).to_have_value("action")
    expect(page.get_by_role("button", name="Paginated")).to_be_visible()
    expect(page.get_by_role("link", name="FDX")).to_have_attribute("href", "/api/v1/projects/9001/screenplays/12/exports/fdx")
    expect(page.get_by_text("artifact:3 · v2")).to_be_visible()
    page.get_by_label("Format action").select_option("dialogue")
    page.get_by_role("button", name="Review format").first.click()
    expect(page.get_by_text("#80 block")).to_be_visible()
    page.get_by_role("button", name="Timeline board →").click()
    lanes = page.get_by_role("region", name="Act and character lanes")
    expect(lanes).to_contain_text("Act One")
    expect(lanes).to_contain_text("MIRA")
    expect(page.get_by_text("PROPOSED PROPOSAL")).to_be_visible()
    page.get_by_role("button", name="← Editor").click()
    page.get_by_role("button", name="Backups").click()
    expect(page.get_by_role("heading", name="Project backups")).to_be_visible()
    expect(page.get_by_text(backup["filename"])).to_be_visible()
    page.get_by_role("checkbox", name="Heading").uncheck()
    page.get_by_role("button", name="Restore", exact=True).click()
    page.get_by_role("button", name="Run review").click()
    expect(page.get_by_label("Screenplay runtime")).to_be_visible()
    expect(page.get_by_text("Pacing:")).to_be_visible()
    expect(page.locator(".scene-duration")).to_have_text("00:30")
    expect(page.locator(".semantic-row.dual-block")).to_be_visible()
    expect(page.get_by_label("Screenplay formatting toolbar")).to_be_visible()
    editor = page.get_by_label("Edit action")
    expect(editor).to_have_value("The house breathes in the dark.")
    editor.fill("The house exhales in the dark.")
    editor.select_text()
    page.get_by_role("button", name="Bold text").click()
    expect(editor).to_have_value("**The house exhales in the dark.**")
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
    def artifact_update(route: Route) -> None:
        """Validate optimistic text edits and typed story operations."""
        if route.request.method == "POST":
            assert route.request.headers.get("if-match") == "2"
            assert route.request.post_data_json == {
                "operation": "set_logline",
                "payload": {"text": "A family returns to a house that remembers."},
            }
            route.fulfill(status=200, content_type="application/json", body=json.dumps({**artifact, "content": "A family returns to a house that remembers.", "version": 3}))
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(artifact))

    page.route("**/api/v1/projects/9001/artifacts/31", artifact_update)
    page.goto("/projects/9001/studio")
    expect(page.get_by_role("heading", name="Creative artifacts")).to_be_visible()
    expect(page.get_by_label("New artifact kind")).to_have_value("brief")
    expect(page.get_by_role("button", name="brief First pass STALE")).to_be_visible()
    content = page.get_by_label("Artifact content")
    content.fill("A family returns to a house that remembers.")
    content.blur()
    page.get_by_label("Operation logline").fill("A family returns to a house that remembers.")
    page.get_by_role("button", name="Apply structured decision").click()


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
    def respond(route: Route) -> None:
        """Validate the context envelope sent by the story-studio Copilot."""
        payload = route.request.post_data_json
        assert payload["page"] == "/projects/9001/studio"
        assert payload["artifact"] == "brief"
        assert payload["selection"] == "First pass"
        route.fulfill(status=202, content_type="application/json", body=json.dumps({"message": {"id": 30, "project_id": 9001, "role": "user", "content": "Find the gap.", "page": "studio", "artifact": "brief", "selection": "First pass", "instruction_layers": {"agent_role": "story_architect", "permission_mode": "chat_only", "provider_profile_id": None}, "citations": [], "active_tools": [], "created_at": "2026-01-01T00:00:00Z"}, "run": {"id": 44, "project_id": 9001, "kind": "copilot_response", "status": "queued", "result": None, "error": None}}))

    page.route("**/api/v1/projects/9001/copilot/messages/respond-async", respond)
    page.route("**/api/v1/projects/9001/runs/44", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"id": 44, "project_id": 9001, "kind": "copilot_response", "status": "succeeded", "result": {"assistant_message_id": 32}, "error": None})))
    page.goto("/projects/9001/studio")
    page.get_by_label("Copilot message").fill("Find the gap.")
    page.get_by_role("button", name="Send").click()
    expect(page.get_by_text("The reveal needs a setup.")).to_be_visible()


def test_context_page_creates_typed_knowledge_node(page: Page) -> None:
    """Create a project-scoped creative-context node through the React page."""
    graph = {"nodes": [], "edges": []}
    created = {"id": 40, "project_id": 9001, "kind": "film", "label": "Pather Panchali", "description": "Textured rural reference.", "node_metadata": {}, "version": 1}

    def graph_request(route: Route) -> None:
        """Return the current mocked graph."""
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"nodes": [created] if graph["nodes"] else [], "edges": []}))

    def create_node(route: Route) -> None:
        """Validate and persist the mocked graph node."""
        assert route.request.post_data_json == {"kind": "film", "label": "Pather Panchali", "description": "Textured rural reference."}
        graph["nodes"].append(created)
        route.fulfill(status=201, content_type="application/json", body=json.dumps(created))

    def update_node(route: Route) -> None:
        """Validate the optimistic canonical-node update."""
        assert route.request.headers.get("if-match") == "1"
        route.fulfill(status=200, content_type="application/json", body=json.dumps({**created, "label": "Pather Panchali revised", "version": 2}))

    page.route("**/api/v1/projects/9001/knowledge-graph", graph_request)
    page.route("**/api/v1/projects/9001/context/workflows", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/projects/9001/artifacts", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/projects/9001/knowledge-graph/nodes", create_node)
    page.route("**/api/v1/projects/9001/knowledge-graph/nodes/40", update_node)
    page.route("**/api/v1/projects/9001/copilot/messages", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/agents/roles", lambda route: route.fulfill(status=200, content_type="application/json", body='[{"key":"story_architect","label":"Story architect","description":"Shape the story.","default_permission":"chat_only"}]'))
    page.route("**/api/v1/settings/providers", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.goto("/projects/9001/context?kind=film")
    expect(page.get_by_label("Context node type")).to_have_value("film")
    page.get_by_label("Context node label").fill("Pather Panchali")
    page.get_by_label("Context node description").fill("Textured rural reference.")
    page.get_by_role("button", name="Add context").click()
    expect(page.get_by_label("Edit Pather Panchali label")).to_have_value("Pather Panchali")
    label = page.get_by_label("Edit Pather Panchali label")
    label.fill("Pather Panchali revised")
    label.blur()


def test_context_page_links_project_nodes(page: Page) -> None:
    """Link two project-scoped creative-context nodes through the React page."""
    nodes = [
        {"id": 40, "project_id": 9001, "kind": "film", "label": "Pather Panchali", "description": None, "node_metadata": {}, "version": 1},
        {"id": 41, "project_id": 9001, "kind": "character", "label": "Apu", "description": None, "node_metadata": {}, "version": 1},
    ]
    graph = {"nodes": nodes, "edges": []}

    def graph_request(route: Route) -> None:
        """Return the current mocked graph for the project."""
        route.fulfill(status=200, content_type="application/json", body=json.dumps(graph))

    def create_edge(route: Route) -> None:
        """Validate and persist the mocked relationship."""
        assert route.request.post_data_json == {"source_node_id": 40, "target_node_id": 41, "relation": "inspires"}
        edge = {"id": 70, "project_id": 9001, "source_node_id": 40, "target_node_id": 41, "relation": "inspires", "edge_metadata": {}}
        graph["edges"].append(edge)
        route.fulfill(status=201, content_type="application/json", body=json.dumps(edge))

    def delete_edge(route: Route) -> None:
        """Delete the mocked relationship."""
        graph["edges"].clear()
        route.fulfill(status=204)

    page.route("**/api/v1/projects/9001/knowledge-graph", graph_request)
    page.route("**/api/v1/projects/9001/context/workflows", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/projects/9001/artifacts", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/projects/9001/knowledge-graph/edges", create_edge)
    page.route("**/api/v1/projects/9001/knowledge-graph/edges/70", delete_edge)
    page.route("**/api/v1/projects/9001/copilot/messages", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/agents/roles", lambda route: route.fulfill(status=200, content_type="application/json", body='[{"key":"story_architect","label":"Story architect","description":"Shape the story.","default_permission":"chat_only"}]'))
    page.route("**/api/v1/settings/providers", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.goto("/projects/9001/context")
    page.get_by_label("Relationship source").select_option("40")
    page.get_by_label("Relationship type").fill("inspires")
    page.get_by_label("Relationship target").select_option("41")
    page.get_by_role("button", name="Link nodes").click()
    relationship = page.locator(".graph-edge")
    expect(relationship).to_contain_text("Pather Panchali")
    expect(relationship).to_contain_text("inspires")
    expect(relationship).to_contain_text("Apu")
    page.get_by_role("button", name="Delete relationship inspires").click()
    expect(relationship).not_to_be_visible()


def test_context_page_edits_versioned_project_reference(page: Page) -> None:
    """Edit and remove a typed project reference through the React context page."""
    reference = {"id": 12, "project_id": 9001, "kind": "film", "label": "Pather Panchali", "url": "https://example.test/pather", "note": "Texture", "version": 1}
    deleted = {"value": False}

    def references(route: Route) -> None:
        """Return the current project reference."""
        route.fulfill(status=200, content_type="application/json", body=json.dumps([] if deleted["value"] else [reference]))

    def update_reference(route: Route) -> None:
        """Validate the reference optimistic concurrency header and update it."""
        assert route.request.headers.get("if-match") == "1"
        assert route.request.post_data_json["label"] == "Pather Panchali revised"
        reference.update(label="Pather Panchali revised", version=2)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(reference))

    def delete_reference(route: Route) -> None:
        """Delete the project reference."""
        deleted["value"] = True
        route.fulfill(status=204)

    page.route("**/api/v1/projects/9001/references", references)
    page.route("**/api/v1/projects/9001/references/12", lambda route: update_reference(route) if route.request.method == "PATCH" else delete_reference(route))
    page.route("**/api/v1/projects/9001/knowledge-graph", lambda route: route.fulfill(status=200, content_type="application/json", body='{"nodes": [], "edges": []}'))
    page.route("**/api/v1/projects/9001/copilot/messages", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/agents/roles", lambda route: route.fulfill(status=200, content_type="application/json", body='[{"key":"story_architect","label":"Story architect","description":"Shape the story.","default_permission":"chat_only"}]'))
    page.route("**/api/v1/settings/providers", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.goto("/projects/9001/context")
    reference_label = page.locator(".reference-card input").first
    expect(reference_label).to_have_value("Pather Panchali")
    reference_label.fill("Pather Panchali revised")
    page.get_by_role("button", name="Save").click()
    expect(reference_label).to_have_value("Pather Panchali revised")
    page.on("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Remove").click()
    expect(page.locator(".reference-card")).not_to_be_visible()


def test_timeline_supports_drag_keyboard_reorder_and_proposal(page: Page) -> None:
    """Reorder scenes visually and with keyboard controls before proposing approval."""
    project = {"id": 9001, "title": "Timeline story", "logline": "A reordered story.", "description": "", "genres": ["Drama"], "languages": ["English"], "primary_language": "English", "project_instruction": "", "version": 1, "artwork_url": None}
    scenes = [
        {"id": 7, "act_id": 4, "heading": "INT. HOUSE - NIGHT", "position": 0, "body": "MIRA waits." , "version": 1, "scene_instruction": ""},
        {"id": 8, "act_id": 4, "heading": "EXT. GARDEN - DAWN", "position": 1, "body": "MIRA runs.", "version": 1, "scene_instruction": ""},
    ]
    workspace = {"project": project, "screenplay": {"id": 12, "project_id": 9001, "title": "Timeline story", "format": "feature", "status": "draft"}, "acts": [{"id": 4, "screenplay_id": 12, "title": "Act One", "position": 0}], "scenes": scenes, "blocks": {"7": [{"id": 20, "scene_id": 7, "position": 0, "element_type": "character", "text": "MIRA", "character_extension": None, "is_dual": False, "dual_group": None, "translation": None, "translation_lang": None}], "8": [{"id": 21, "scene_id": 8, "position": 0, "element_type": "character", "text": "MIRA", "character_extension": None, "is_dual": False, "dual_group": None, "translation": None, "translation_lang": None}]}}
    proposal = {"id": 91, "project_id": 9001, "screenplay_id": 12, "status": "proposed", "original_scene_ids": [7, 8], "proposed_scene_ids": [8, 7], "timings": [{"scene_id": 8, "position": 0, "start_seconds": 0, "end_seconds": 30}, {"scene_id": 7, "position": 1, "start_seconds": 30, "end_seconds": 60}], "total_runtime_seconds": 60}

    page.route("**/api/v1/projects/9001/workspace", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(workspace)))
    def timeline_proposals(route: Route) -> None:
        """Serve the isolated timeline proposal lifecycle fixture."""
        if route.request.method == "GET":
            route.fulfill(status=200, content_type="application/json", body="[]")
            return
        route.fulfill(status=201, content_type="application/json", body=json.dumps(proposal))

    def timeline_mutation(route: Route) -> None:
        """Approve and rollback the timeline fixture without a live database."""
        if route.request.url.endswith("/approve"):
            proposal["status"] = "approved"
        elif route.request.url.endswith("/rollback"):
            proposal["status"] = "rolled_back"
        route.fulfill(status=200, content_type="application/json", body=json.dumps(proposal))

    page.route("**/api/v1/projects/9001/screenplays/12/timeline/proposals", timeline_proposals)
    page.route("**/api/v1/projects/9001/screenplays/12/timeline/proposals/91/approve", timeline_mutation)
    page.route("**/api/v1/projects/9001/screenplays/12/timeline/proposals/91/rollback", timeline_mutation)
    page.route("**/api/v1/projects/9001/agent-proposals", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/projects/9001/copilot/messages", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/agents/roles", lambda route: route.fulfill(status=200, content_type="application/json", body='[{"key":"story_architect","label":"Story architect","description":"Shape the story.","default_permission":"chat_only"}]'))
    page.route("**/api/v1/settings/providers", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.goto("/projects/9001")
    page.get_by_role("button", name="Timeline board →").click()
    cards = page.locator(".timeline-card")
    expect(cards.nth(0)).to_contain_text("INT. HOUSE")
    cards.nth(1).drag_to(cards.nth(0))
    expect(cards.nth(0)).to_contain_text("EXT. GARDEN")
    page.get_by_role("button", name="Move EXT. GARDEN - DAWN later").click()
    expect(cards.nth(0)).to_contain_text("INT. HOUSE")
    page.get_by_role("button", name="Move EXT. GARDEN - DAWN earlier").click()
    expect(cards.nth(0)).to_contain_text("EXT. GARDEN")
    page.get_by_role("button", name="Review reorder").click()
    expect(page.get_by_text("PROPOSED PROPOSAL")).to_be_visible()
    page.get_by_role("button", name="Approve reorder").click()
    expect(page.get_by_text("APPROVED PROPOSAL")).to_be_visible()
    page.get_by_role("button", name="Rollback reorder").click()
    expect(page.get_by_text("ROLLED_BACK PROPOSAL")).to_be_visible()


def test_context_workflow_is_review_only_and_reconnectable(page: Page) -> None:
    """Review and explicitly apply a mocked context-generation run after reconnecting."""
    artifact = {"id": 31, "project_id": 9001, "kind": "outline", "title": "Outline", "content": "The reveal happens.", "version": 4, "stale": False, "depends_on": [], "artifact_metadata": {}}
    workflow = {"key": "camera", "label": "Camera plan", "description": "Plan coverage.", "input_artifact_kinds": ["outline"], "output_kind": "camera", "evaluator": "production_feasibility_review", "agent_role": "associate_director", "permission_mode": "suggest"}

    page.route("**/api/v1/projects/9001/knowledge-graph", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"nodes": [], "edges": []})))
    page.route("**/api/v1/projects/9001/references", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/projects/9001/context/workflows", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps([workflow])))
    page.route("**/api/v1/projects/9001/artifacts", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps([artifact])))
    page.route("**/api/v1/projects/9001/copilot/messages", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/agents/roles", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    page.route("**/api/v1/settings/providers", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))

    def start_run(route: Route) -> None:
        """Validate the typed context workflow request."""
        assert route.request.post_data_json == {"workflow": "camera", "artifact_id": 31, "instruction": "Plan coverage for the reveal.", "permission_mode": "suggest"}
        route.fulfill(status=202, content_type="application/json", body=json.dumps({"id": 44, "project_id": 9001, "kind": "context_generation", "status": "queued", "result": None, "error": None}))

    def read_run(route: Route) -> None:
        """Return a completed review-only result after the worker poll."""
        result = {"workflow": "camera", "output_kind": "camera", "suggestion": "Use a slow push into the reveal.", "citations": [{"source_id": "artifact:31", "content_version": 4}], "source_version": 4, "requires_review": True}
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"id": 44, "project_id": 9001, "kind": "context_generation", "status": "succeeded", "result": result, "error": None}))

    def apply_run(route: Route) -> None:
        """Validate explicit source-version approval and return the graph node."""
        assert route.request.post_data_json == {"expected_source_version": 4}
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"id": 51, "project_id": 9001, "kind": "camera", "label": "Camera from run 44", "description": "Use a slow push into the reveal.", "node_metadata": {"source_run_id": 44}, "version": 1}))

    page.route("**/api/v1/projects/9001/context/workflows/runs", start_run)
    page.route("**/api/v1/projects/9001/context/workflows/runs/44/apply", apply_run)
    page.route("**/api/v1/projects/9001/runs/44", read_run)
    page.goto("/projects/9001/context")
    page.get_by_label("Context workflow instruction").fill("Plan coverage for the reveal.")
    page.get_by_role("button", name="Generate review suggestion").click()
    expect(page.get_by_text("Use a slow push into the reveal.")).to_be_visible()
    expect(page.get_by_text("Retrieved citations attached · output kind: camera")).to_be_visible()
    page.get_by_role("button", name="Apply to knowledge graph").click()
    expect(page.get_by_text("Applied as a new versioned graph node.")).to_be_visible()
