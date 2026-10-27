"""Run the ``develop_story`` pipeline on a running stack and approve every stage as the writer.

    uv run python scripts/develop_story_journey.py                 # against http://localhost:9000
    DRAFTPILOT_API=... uv run python scripts/develop_story_journey.py "An idea to develop"

It creates a project, starts ``develop_story`` with a small cast and one drafted beat, approves each
stage's proposals as they arrive (the pipeline waits for them), and prints what the room built.
Needs the worker and a model (LM Studio by default); a run takes several minutes on a local model.
"""

import asyncio
import os
import sys
import time
from typing import Any

import httpx

API = os.environ.get("DRAFTPILOT_API", "http://localhost:9000/api/v1")
API_TOKEN = os.environ.get("API__TOKEN", "")
IDEA = (
    "A lighthouse keeper's daughter on a storm-bound island must let the light go dark for one night "
    "to lure a smuggler's ship onto the rocks, knowing her father's life depends on it burning."
)
DONE = {"completed", "succeeded", "failed", "cancelled", "canceled", "timed_out"}


async def journey(idea: str) -> None:
    """Create a project, run the pipeline, approve each stage and report the result."""
    headers = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=60) as api:
        project = (await api.post("/projects", json={"title": "Pipeline journey: The Dark Light", "logline": idea[:200]})).json()
        pid = project["id"]
        params = {"idea": idea, "cast_size": 2, "outline_rounds": 1, "draft_beats": 1}
        response = await api.post(f"/projects/{pid}/room/workflows", json={"workflow": "develop_story", "params": params})
        response.raise_for_status()
        run = response.json()
        print(f"project {pid}, run {run['id']}")
        started, approved = time.monotonic(), 0
        while run["status"] not in DONE:
            await asyncio.sleep(10)
            pending = [
                item
                for item in (await api.get(f"/projects/{pid}/agent-proposals")).json()
                if item["run_id"] == run["id"] and item["status"] == "proposed"
            ]
            for item in pending:
                (await api.post(f"/projects/{pid}/agent-proposals/{item['id']}/approve")).raise_for_status()
                approved += 1
                print(f"  {time.monotonic() - started:5.0f}s approved {item['target_kind']} proposal {item['id']}")
            run = (await api.get(f"/projects/{pid}/runs/{run['id']}")).json()
        print(f"run {run['status']} after {time.monotonic() - started:.0f}s with {approved} approvals")
        if run["status"] not in {"completed", "succeeded"}:
            raise SystemExit(f"pipeline failed: {run.get('error')}")
        story: dict[str, Any] = (await api.get(f"/projects/{pid}/storyline")).json()
        characters = (await api.get(f"/projects/{pid}/characters")).json()
        beats = (await api.get(f"/projects/{pid}/beats")).json()
        print(f"storyline: {story.get('premise') or story.get('logline')}")
        for character in characters:
            events = (await api.get(f"/projects/{pid}/characters/{character['id']}/timeline")).json()
            print(f"  {character['name']} ({character['role']}): wants {character['want']!r}; {len(events)} timeline moments")
        print(f"{len(beats)} beats, {sum(bool(beat['scene_ids']) for beat in beats)} linked to scenes")
        assert characters and beats, "the pipeline left no cast or outline"


if __name__ == "__main__":
    try:
        asyncio.run(journey(sys.argv[1] if len(sys.argv) > 1 else IDEA))
    except (AssertionError, httpx.HTTPError) as exc:
        print(f"journey failed: {exc}", file=sys.stderr)
        sys.exit(1)
