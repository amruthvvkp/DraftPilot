"""Exercise the primary DraftPilot workflow in one isolated browser journey."""

import json
import re

from playwright.sync_api import Page, Route, expect


def test_writer_smoke_journey_from_project_to_recovery(page: Page) -> None:
    """Complete the mocked writer journey without using the application database."""
    project = {
        "id": 42,
        "title": "Monsoon House",
        "logline": "A family returns to a house that remembers.",
        "description": "A multilingual family drama.",
        "genres": ["Drama"],
        "languages": ["Hindi", "Bengali"],
        "primary_language": "Hindi",
        "project_instruction": "Keep the family history grounded.",
        "version": 1,
        "artwork_url": None,
    }
    scenes = [
        {"id": 101, "act_id": 10, "heading": "INT. HOUSE - NIGHT", "position": 0, "body": "MIRA waits.", "version": 1, "scene_instruction": ""},
        {"id": 102, "act_id": 10, "heading": "EXT. COURTYARD - DAWN", "position": 1, "body": "The rain stops.", "version": 1, "scene_instruction": ""},
    ]
    blocks = {
        "101": [
            {"id": 201, "scene_id": 101, "position": 0, "element_type": "action", "text": "MIRA waits.", "character_extension": None, "is_dual": False, "dual_group": None, "translation": None, "translation_lang": None},
            {"id": 202, "scene_id": 101, "position": 1, "element_type": "dialogue", "text": "We should go.", "character_extension": None, "is_dual": False, "dual_group": None, "translation": None, "translation_lang": None},
            {"id": 203, "scene_id": 101, "position": 2, "element_type": "character", "text": "MIRA", "character_extension": None, "is_dual": False, "dual_group": None, "translation": None, "translation_lang": None},
        ],
        "102": [],
    }
    workspace = {"project": project, "screenplay": {"id": 12, "project_id": 42, "title": project["title"], "format": "feature", "status": "draft"}, "acts": [{"id": 10, "screenplay_id": 12, "title": "Act One", "position": 0}], "scenes": scenes, "blocks": blocks}
    artifacts = [{"id": 301, "project_id": 42, "kind": "brief", "title": "Brief", "content": project["logline"], "version": 1, "stale": False, "depends_on": [], "artifact_metadata": {}}]
    proposals: list[dict[str, object]] = []
    translations: list[dict[str, object]] = []
    timeline = {"id": 501, "project_id": 42, "screenplay_id": 12, "status": "proposed", "original_scene_ids": [101, 102], "proposed_scene_ids": [102, 101], "timings": [{"scene_id": 102, "position": 0, "start_seconds": 0, "end_seconds": 30}, {"scene_id": 101, "position": 1, "start_seconds": 30, "end_seconds": 60}], "total_runtime_seconds": 60}
    backup = {"filename": "42-20260904T000000Z.json.gz", "manifest": {"schema_version": 1, "project_id": 42, "created_at": "2026-09-04T00:00:00Z", "app_version": "0.1.0", "sha256": "a" * 64}}

    def respond(route: Route) -> None:
        """Serve and mutate only the journey's in-memory fixture state."""
        request = route.request
        path = request.url.split("/api/v1", 1)[-1].split("?", 1)[0]
        payload = request.post_data_json if request.post_data else {}
        result: object = []
        code = 200
        if path == "/projects" and request.method == "POST":
            assert payload["primary_language"] == "Hindi"
            assert payload["languages"] == ["Bengali"]
            result, code = project, 201
        elif path == "/projects":
            result = []
        elif path.endswith("/workspace"):
            result = workspace
        elif path == "/projects/42/artifacts" and request.method == "POST":
            next_id = 302 + len(artifacts)
            item = {"id": next_id, "project_id": 42, "kind": payload["kind"], "title": payload["title"], "content": "", "version": 1, "stale": False, "depends_on": payload.get("depends_on", []), "artifact_metadata": {}}
            artifacts.append(item)
            result, code = item, 201
        elif path == "/projects/42/artifacts":
            result = artifacts
        elif "/artifacts/301/operations" in path:
            artifacts[0]["version"] = 2
            artifacts[0]["content"] = payload["payload"].get("text", artifacts[0]["content"])
            result = artifacts[0]
        elif "/artifacts/301" in path and request.method == "PATCH":
            artifacts[0]["version"] = 2
            artifacts[0]["content"] = payload.get("content", artifacts[0]["content"])
            result = artifacts[0]
        elif path.endswith("/agent-proposals") and request.method == "POST":
            proposal = {"id": 701, "project_id": 42, "run_id": None, "target_kind": payload["target_kind"], "target_id": payload["target_id"], "operation": payload["operation"], "diff": payload.get("diff", {}), "before": {}, "base_version": payload["base_version"], "status": "proposed"}
            proposals[:] = [proposal]
            result, code = proposal, 201
        elif path.endswith("/agent-proposals"):
            result = proposals
        elif path.endswith("/agent-proposals/701/approve"):
            proposals[0]["status"] = "approved"
            result = proposals[0]
        elif path.endswith("/agent-proposals/701/rollback"):
            proposals[0]["status"] = "rolled_back"
            result = proposals[0]
        elif "/translations/" in path and request.method == "PUT":
            item = {"id": 801, "block_id": 202, "language": "Bengali", "text": payload["text"], "source_version": 1, "status": "draft"}
            translations[:] = [item]
            result, code = item, 200
        elif "/translations" in path:
            result = translations
        elif "/timeline/proposals" in path and path.endswith("/approve"):
            timeline["status"] = "approved"
            result = timeline
        elif "/timeline/proposals" in path and path.endswith("/rollback"):
            timeline["status"] = "rolled_back"
            result = timeline
        elif "/timeline/proposals" in path and request.method == "POST":
            result, code = timeline, 201
        elif "/timeline/proposals" in path:
            result = []
        elif path.endswith("/backups") and request.method == "POST":
            result, code = backup, 201
        elif path.endswith("/backups"):
            result = [backup]
        elif "/backups/" in path and path.endswith("/restore"):
            result = {"project_id": 43}
        elif path.endswith("/runs/55"):
            result = {"id": 55, "project_id": 42, "kind": "evaluation", "status": "succeeded", "result": {}, "error": None}
        elif path.endswith("/evaluations/runs"):
            result, code = {"id": 55, "project_id": 42, "kind": "evaluation", "status": "queued", "result": None, "error": None}, 202
        elif path.endswith(("/evaluations", "/copilot/messages")):
            result = []
        elif path.endswith("/agents/roles"):
            result = [{"key": "story_architect", "label": "Story architect", "description": "Shape the story.", "default_permission": "chat_only"}]
        elif path.endswith(("/settings/providers", "/capabilities", "/revisions")):
            result = []
        route.fulfill(status=code, content_type="application/json", body=json.dumps(result))

    page.route("**/api/v1/**", respond)
    page.goto("/projects")
    page.get_by_role("button", name="New project").first.click()
    wizard = page.locator(".wizard")
    wizard.get_by_label("Project title").fill("Monsoon House")
    wizard.get_by_role("button", name="Drama", exact=True).click()
    wizard.get_by_role("button", name="Continue").click()
    wizard.get_by_label("Primary screenplay language").select_option(label="Hindi")
    wizard.get_by_role("button", name="Bengali", exact=True).click()
    wizard.get_by_role("button", name="Continue").click()
    wizard.get_by_role("button", name="Continue").click()
    wizard.get_by_role("button", name="Create project", exact=False).click()
    expect(page).to_have_url(re.compile(r"/projects/42$"))
    page.get_by_role("button", name="Story studio ↗").click()
    expect(page.get_by_role("heading", name="Creative artifacts")).to_be_visible()
    page.get_by_label("New artifact kind").select_option("outline")
    page.get_by_role("button", name="＋ Add").click()
    page.get_by_label("New artifact kind").select_option("character")
    page.get_by_role("button", name="＋ Add").click()
    page.get_by_role("button", name="← Screenplay").click()
    expect(page.get_by_role("heading", name="Monsoon House")).to_be_visible()
    editor = page.get_by_label("Edit action")
    editor.fill("MIRA waits beneath the monsoon sky.")
    editor.press("Tab")
    expect(page.get_by_label("Edit dialogue")).to_be_focused()
    editor.blur()
    page.get_by_label("Dialogue translation language").select_option("Bengali")
    page.get_by_label("Edit Bengali translation").fill("আমাদের যেতে হবে।")
    page.get_by_label("Edit Bengali translation").blur()
    page.get_by_label("Format action").select_option("dialogue")
    page.get_by_role("button", name="Review format").first.click()
    expect(page.get_by_text("#701 block")).to_be_visible()
    page.get_by_role("button", name="Approve change").click()
    page.get_by_role("button", name="Rollback").click()
    page.get_by_role("button", name="Timeline board →").click()
    page.get_by_role("button", name="Review reorder").click()
    page.get_by_role("button", name="Approve reorder").click()
    page.get_by_role("button", name="Rollback reorder").click()
    page.get_by_role("button", name="← Editor").click()
    expect(page.get_by_role("link", name="FDX")).to_have_attribute("href", "/api/v1/projects/42/screenplays/12/exports/fdx")
    page.get_by_role("button", name="Backup", exact=True).click()
    page.get_by_role("button", name="Backups").click()
    page.get_by_role("button", name="Restore copy").click()
    expect(page).to_have_url(re.compile(r"/projects/43$"))
