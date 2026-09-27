"""Test whole-scene rewrite proposals: parse, propose, approve, and roll back against a real database."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from _async import run_async
from _db import memory_session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.api.agent import router
from draftpilot.core.db import async_get_db
from draftpilot.core.scene_proposals import (
    append_operation,
    parse_scene_fountain,
    rewrite_operation,
)
from draftpilot.core.screenplay.hydrate import blocks_for_scene
from draftpilot.crud import scenes as scenes_crud
from draftpilot.models import (
    Act,
    AgentProposal,
    Block,
    BlockType,
    Project,
    Scene,
    Screenplay,
)

REWRITE = """INT. WILL'S BEDROOM - NIGHT

Will lies awake, listening.

EDWARD (O.S.)
You awake, kiddo?

WILL
No.
"""


def test_fountain_rewrite_parses_to_one_scene_without_ids() -> None:
    """A Fountain scene becomes a heading plus typed blocks that carry no ids."""
    doc = parse_scene_fountain(REWRITE)
    assert doc.heading == "INT. WILL'S BEDROOM - NIGHT"
    assert [block.element_type for block in doc.blocks][:3] == [BlockType.ACTION, BlockType.CHARACTER, BlockType.DIALOGUE]
    assert all(block.id is None for block in doc.blocks)
    with pytest.raises(ValueError):
        parse_scene_fountain("   ")


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, AsyncSession]:
    """Serve the proposal router over one seeded scene with a translated block."""
    monkeypatch.setattr("draftpilot.api.agent.scene_changed", AsyncMock())
    monkeypatch.setattr("draftpilot.api.agent.events.publish", AsyncMock())
    monkeypatch.setattr("draftpilot.crud.agent_proposals.events.publish", AsyncMock())
    context = memory_session()
    session = run_async(context.__aenter__())

    async def seed() -> None:
        """Persist one scene with two writer-authored blocks."""
        project = Project(title="Big Fish")
        session.add(project)
        await session.flush()
        screenplay = Screenplay(project_id=project.id or 0, title="Big Fish")
        session.add(screenplay)
        await session.flush()
        act = Act(screenplay_id=screenplay.id or 0)
        session.add(act)
        await session.flush()
        scene = Scene(act_id=act.id or 0, heading="INT. BEDROOM - NIGHT", version=2)
        session.add(scene)
        await session.flush()
        session.add_all(
            [
                Block(scene_id=scene.id or 0, position=0, text="Will sleeps.", origin="human"),
                Block(scene_id=scene.id or 0, position=1, text="A knock.", origin="human"),
            ]
        )
        await session.commit()

    run_async(seed())
    app = FastAPI()

    async def dependency() -> AsyncGenerator[AsyncSession]:
        """Yield the shared seeded session."""
        yield session

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(router, prefix="/api/v1")
    yield TestClient(app), session
    run_async(context.__aexit__(None, None, None))


def test_rewrite_proposal_replaces_blocks_on_approval_and_restores_them_on_rollback(
    seeded: tuple[TestClient, AsyncSession],
) -> None:
    """Nothing changes until approval; approval rewrites with authorship; rollback restores the writer's text."""
    client, session = seeded
    created = client.post(
        "/api/v1/projects/1/agent-proposals",
        json={
            "target_kind": "scene",
            "target_id": 1,
            "operation": rewrite_operation(parse_scene_fountain(REWRITE)),
            "base_version": 2,
        },
    )
    assert created.status_code == 201, created.text
    proposal = created.json()
    assert [block["text"] for block in proposal["before"]["blocks"]] == ["Will sleeps.", "A knock."]
    assert [block.text for block in run_async(blocks_for_scene(session, 1))] == ["Will sleeps.", "A knock."]

    approved = client.post(f"/api/v1/projects/1/agent-proposals/{proposal['id']}/approve")
    assert approved.status_code == 200, approved.text
    blocks = run_async(blocks_for_scene(session, 1))
    assert [block.text for block in blocks] == ["Will lies awake, listening.", "EDWARD", "You awake, kiddo?", "WILL", "No."]
    assert {block.origin for block in blocks} == {f"proposal:{proposal['id']}"}
    assert blocks[0].id == 1  # blocks are updated in place, so ids stay stable
    scene = run_async(session.get(Scene, 1))
    assert scene is not None and scene.heading == "INT. WILL'S BEDROOM - NIGHT" and scene.version == 3

    rolled = client.post(f"/api/v1/projects/1/agent-proposals/{proposal['id']}/rollback")
    assert rolled.status_code == 200, rolled.text
    blocks = run_async(blocks_for_scene(session, 1))
    assert [(block.text, block.origin) for block in blocks] == [("Will sleeps.", "human"), ("A knock.", "human")]
    assert scene.heading == "INT. BEDROOM - NIGHT" and scene.version == 4


def test_invalid_rewrite_payloads_are_rejected(seeded: tuple[TestClient, AsyncSession]) -> None:
    """Rewrites must carry valid blocks and cannot be mixed with a body edit."""
    client, _session = seeded
    for operation in ({"blocks": []}, {"blocks": [{"element_type": "nope"}]}, {"blocks": [{"text": "x"}], "body": "y"}):
        response = client.post(
            "/api/v1/projects/1/agent-proposals",
            json={"target_kind": "scene", "target_id": 1, "operation": operation, "base_version": 2},
        )
        assert response.status_code == 422, operation


def test_appended_scenes_land_after_the_last_scene_and_roll_back_until_edited(
    seeded: tuple[TestClient, AsyncSession],
) -> None:
    """Approving an append creates proposal-authored scenes; rollback removes them; edited scenes block rollback."""
    client, session = seeded
    new_scene = parse_scene_fountain(REWRITE)

    async def propose() -> int:
        """Persist two append proposals the way the room gate does."""
        ids = []
        for _ in range(2):
            proposal = AgentProposal(
                project_id=1, target_kind="screenplay", target_id=1, operation=append_operation([new_scene]), base_version=1
            )
            session.add(proposal)
            await session.commit()
            ids.append(proposal.id or 0)
        return ids

    first, second = run_async(propose())
    approved = client.post(f"/api/v1/projects/1/agent-proposals/{first}/approve")
    assert approved.status_code == 200, approved.text
    created = approved.json()["diff"]["created_scene_ids"]
    scenes = run_async(scenes_crud.list_for_screenplay(session, 1))
    assert [scene.heading for scene in scenes] == ["INT. BEDROOM - NIGHT", "INT. WILL'S BEDROOM - NIGHT"]
    blocks = run_async(blocks_for_scene(session, created[0]))
    assert {block.origin for block in blocks} == {f"proposal:{first}"} and len(blocks) == 5

    assert client.post(f"/api/v1/projects/1/agent-proposals/{first}/rollback").status_code == 200
    assert len(run_async(scenes_crud.list_for_screenplay(session, 1))) == 1

    assert client.post(f"/api/v1/projects/1/agent-proposals/{second}/approve").status_code == 200
    edited = run_async(scenes_crud.list_for_screenplay(session, 1))[-1]
    edited.version = 2
    session.add(edited)
    run_async(session.commit())
    assert client.post(f"/api/v1/projects/1/agent-proposals/{second}/rollback").status_code == 409
