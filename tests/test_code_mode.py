"""Test Monty code mode: exact script analysis, sandbox limits, continuity rules, audits and gating."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from _async import run_async
from fastmcp import Client
from fastmcp.exceptions import ToolError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from test_room_workflows import _run, project  # noqa: F401 - project is a fixture

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.runtime import CODE_TOOLS, code_mode_active
from draftpilot.core.agent_identity import InternalAgent, identity_meta
from draftpilot.core.config import settings
from draftpilot.core.continuity_rules import (
    RULES,
    check_continuity_rules,
    rules_program,
)
from draftpilot.core.monty import (
    MontyDisabledError,
    MontyExecutionConfig,
    MontySandboxError,
    execute_glue,
)
from draftpilot.core.screenplay.adapters.fountain import parse_fountain
from draftpilot.core.script_analysis import (
    ScriptView,
    StoryView,
    analyze_script,
    host_objects,
    script_view,
)
from draftpilot.models import CharacterTimelineEvent, MontyExecution

BIG_FISH = (Path(__file__).parent / "test_screenplays" / "Big-Fish.fountain").read_text()
SANDBOX = MontyExecutionConfig(enabled=True, max_duration_seconds=2)


@pytest.fixture
def monty_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Switch Monty on for one test, with a roomy time limit."""
    monkeypatch.setattr(settings.monty, "enabled", True)
    monkeypatch.setattr(settings.monty, "max_duration_seconds", 2.0)
    yield


def _big_fish(text: str = BIG_FISH) -> ScriptView:
    """Return the Big Fish script view."""
    return script_view(parse_fountain(text))


def _sandbox(code: str, script: ScriptView, story: StoryView | None = None) -> Any:
    """Run code over the views in the sandbox and return its value."""
    return execute_glue(code, host_objects(script, story or StoryView()), SANDBOX).value


def test_big_fish_stats_are_exact() -> None:
    """Known Big Fish numbers: scenes, speakers, places, dialogue shares and the presence matrix."""
    script = _big_fish()
    summary = script.summary()
    assert (summary["scenes"], summary["speaking_characters"], summary["locations"]) == (191, 48, 148)
    assert summary["words"] == 23713 and summary["dialogue_words"] == 9828 and summary["dialogue_ratio"] == 0.4145
    assert summary["int_ext"]["INT"] == 97 and summary["int_ext"]["EXT"] == 91
    assert summary["times"]["DAY"] == 112 and summary["times"]["NIGHT"] == 50
    assert list(script.dialogue_share())[:3] == ["EDWARD", "WILL", "JENNY"] and script.dialogue_share()["EDWARD"] == 0.454
    assert script.scene(2)["heading"] == "INT.  WILL'S BEDROOM - NIGHT (1973)" and script.scene(2)["year"] == 1973  # type: ignore[index]
    matrix = script.scene_character_matrix(top=2)
    assert matrix["characters"] == ["EDWARD", "WILL"] and sum(matrix["rows"][0]) == len(script.character_scenes("Edward"))
    assert len(script.pacing_curve()) == 191
    # The same numbers, computed by code in the sandbox in one execution.
    value = _sandbox("s = script.summary()\n[s['scenes'], list(script.dialogue_share())[0], len([x for x in script.scenes if x['time'] == 'NIGHT'])]", script)
    assert value == [191, "EDWARD", 50]


def test_sandbox_refuses_escapes_and_enforces_limits() -> None:
    """No private methods, files, imports of the OS, host mutation, runaway loops or memory."""
    script = _big_fish()
    for code in ("script._secret()", "open('/etc/passwd').read()", "import os\nos.listdir('/')", "while True:\n    pass", "x = [0] * (10 ** 9)"):
        with pytest.raises(MontySandboxError):
            _sandbox(code, script)
    # Data crosses by value: changing it inside the sandbox never touches the host's view.
    assert _sandbox("script.scenes[0]['words'] = -1\nscript.scenes[0]['words']", script) == -1
    assert script.scenes[0]["words"] >= 0
    with pytest.raises(MontySandboxError) as failed:
        _sandbox("undefined_name + 1", script)
    assert "NameError" in failed.value.detail and str(failed.value) == "Monty execution failed"
    with pytest.raises(MontyDisabledError):
        execute_glue("script.summary()", host_objects(script, StoryView()))


def test_continuity_rules_catch_a_planted_age_without_false_alarms() -> None:
    """Will is 3 in 1973, 17 in 1987 and 28 in 1998; making him 35 in 1998 is caught, and only that."""
    clean = _sandbox(rules_program(), _big_fish())
    assert clean["errors"] == [] and clean["findings"] == []
    planted = _sandbox(rules_program(scene_ids=[4, 5]), _big_fish(BIG_FISH.replace("now 28", "now 35")))
    assert [(item["rule"], item["kind"], sorted(item["scene_ids"])) for item in planted["findings"]] == [("age_drift", "timeline", [4, 5])]
    assert "35 in 1998" in planted["findings"][0]["description"]
    assert _sandbox(rules_program(scene_ids=[100]), _big_fish(BIG_FISH.replace("now 28", "now 35")))["findings"] == []


def test_continuity_rules_check_the_story_twin_records() -> None:
    """Timeline order, events in the wrong scene, life after death, unknown speakers and places."""
    script = _big_fish()
    elsewhere = next(scene for scene in script.scenes if "WILL" not in scene["speakers"] and "WILL" not in scene["action"].upper())
    story = StoryView(
        characters=[
            {"id": 1, "name": "Will Bloom", "cue": "WILL", "aliases": []},
            {"id": 2, "name": "Edward Bloom", "cue": "EDWARD", "aliases": []},
        ],
        events=[
            {"id": 1, "character_id": 1, "position": 0, "title": "Wedding", "chrono_index": 5.0, "scene_id": 5},
            {"id": 2, "character_id": 1, "position": 1, "title": "Bedtime story", "chrono_index": 1.0, "scene_id": 2},
            {"id": 3, "character_id": 2, "position": 0, "title": "Edward dies", "chrono_index": 9.0, "scene_id": None},
            {"id": 4, "character_id": 2, "position": 1, "title": "Goes fishing", "chrono_index": 10.0, "scene_id": None},
            {"id": 5, "character_id": 1, "position": 2, "title": "At the river", "chrono_index": 2.0, "scene_id": elsewhere["id"]},
        ],
        locations=[{"name": "Bloom Front Hall", "heading_location": "BLOOM FRONT HALL"}],
    )
    result = _sandbox(rules_program(), script, story)
    rules = {item["rule"] for item in result["findings"]}
    assert result["errors"] == []
    assert {"timeline_order", "event_character_absent", "after_death", "speaker_not_in_cast", "location_not_in_story"} <= rules
    absent = next(item for item in result["findings"] if item["rule"] == "event_character_absent")
    assert absent["scene_ids"] == [elsewhere["id"]] and "At the river" in absent["description"]
    assert sum(item["rule"] == "speaker_not_in_cast" for item in result["findings"]) == 8  # capped per rule
    assert {rule.key for rule in RULES} >= rules


def test_a_failing_rule_is_reported_while_the_others_still_run() -> None:
    """One broken rule lands in ``errors``; the rest still return findings."""
    story = StoryView(characters=[{"id": 1, "name": "Will", "cue": "WILL", "aliases": []}], events=[{"id": 1}])
    result = _sandbox(rules_program(), _big_fish(), story)
    assert any(error.startswith(("timeline_order", "event_character_absent")) for error in result["errors"])
    assert any(item["rule"] == "speaker_not_in_cast" for item in result["findings"])


def _audits(session: AsyncSession) -> list[MontyExecution]:
    """Return every Monty audit record."""

    async def query() -> list[MontyExecution]:
        """Select the audit rows."""
        async with AsyncSession(session.bind) as fresh:
            return list((await fresh.exec(select(MontyExecution))).all())

    return run_async(query())


def test_analyze_script_is_audited_on_success_failure_and_refusal(project: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """Every attempt leaves a redacted audit row, including a refusal while Monty is off."""
    with pytest.raises(MontyDisabledError):
        run_async(analyze_script(project, 1, "script.summary()"))
    monkeypatch.setattr(settings.monty, "enabled", True)
    result = run_async(analyze_script(project, 1, "[script.summary()['scenes'], [c['name'] for c in story.characters]]"))
    assert result.value == [1, ["Will", "Edward", "Karl"]]
    with pytest.raises(MontySandboxError):
        run_async(analyze_script(project, 1, "open('secret.txt')"))
    audits = _audits(project)
    assert [audit.status for audit in audits] == ["failed", "completed", "failed"]
    assert all(audit.project_id == 1 and audit.input_count == 2 and len(audit.code_sha256) == 64 for audit in audits)
    assert "secret" not in " ".join(audit.model_dump_json() for audit in audits)


def test_code_tools_go_only_to_code_mode_roles_with_monty_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Code mode needs the role's flag, tools, the run's consent, and MONTY__ENABLED."""
    room = RoomDeps(project_id=1)
    assert CODE_TOOLS == {"analyze_script", "check_continuity_rules"}
    assert not code_mode_active("researcher", room)
    monkeypatch.setattr(settings.monty, "enabled", True)
    assert all(code_mode_active(role, room) for role in ("showrunner", "researcher", "continuity_supervisor", "story_editor", "twin_keeper"))
    assert not code_mode_active("scene_writer", room)
    assert not code_mode_active("researcher", RoomDeps(project_id=1, tools=False))
    assert not code_mode_active("researcher", RoomDeps(project_id=1, code_mode=False))


def test_mcp_code_tools_are_gated_for_external_clients(project: AsyncSession, monty_on: None, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """External clients need MCP__ENABLE_CODE_TOOLS and a grant; the in-app room needs only Monty."""
    from draftpilot.mcp import server

    async def scenario() -> None:
        """Call both tools as an external client and as an in-app agent."""
        async with Client(server.mcp) as client:
            with pytest.raises(ToolError, match="MCP__ENABLE_CODE_TOOLS"):
                await client.call_tool("analyze_script", {"project_id": 1, "code": "1"})
            monkeypatch.setattr(settings.mcp, "enable_code_tools", True)
            with pytest.raises(ToolError, match="not granted"):
                await client.call_tool("analyze_script", {"project_id": 1, "code": "1"})
            meta = identity_meta(InternalAgent(project_id=1, role="researcher"))
            analysed = (await client.call_tool("analyze_script", {"project_id": 1, "code": "script.summary()['scenes']"}, meta=meta)).structured_content
            assert analysed is not None and analysed["value"] == 1
            rules = (await client.call_tool("check_continuity_rules", {"project_id": 1}, meta=meta)).structured_content
            assert rules is not None and rules["errors"] == [] and set(rules["rules"]) == {rule.key for rule in RULES}
            with pytest.raises(ToolError, match="NameError"):
                await client.call_tool("analyze_script", {"project_id": 1, "code": "nope"}, meta=meta)

    run_async(scenario())
    assert [audit.status for audit in _audits(project)] == ["completed", "completed", "failed"]


def _place_karl_in_the_river_scene(session: AsyncSession) -> None:
    """Give Karl a timeline event in scene 1, where he never appears."""

    async def seed() -> None:
        """Persist the event."""
        async with AsyncSession(session.bind) as fresh:
            fresh.add(CharacterTimelineEvent(project_id=1, character_id=3, title="Karl at the river", scene_id=1))
            await fresh.commit()

    run_async(seed())


def test_continuity_workflow_runs_the_rules_in_monty_when_enabled(project: AsyncSession, monty_on: None) -> None:  # noqa: F811
    """The room workflow runs the rules (audited) and hands their findings to the supervisor."""
    _place_karl_in_the_river_scene(project)
    prompts: list[str] = []

    def report(prompt: str, _count: int) -> dict[str, Any]:
        """Record the prompt and confirm the rule's finding."""
        prompts.append(prompt)
        return {"issues": [{"scene_ids": [1], "kind": "character", "description": "Karl is not at the river."}]}

    result, _ = _run("continuity", {}, {"ContinuityReport": report})
    assert result["rules_enabled"] is True
    assert [item["rule"] for item in result["rule_findings"]] == ["event_character_absent"]
    assert "Exact rule checks" in prompts[0] and "Karl at the river" in prompts[0]
    assert [audit.status for audit in _audits(project)] == ["completed"]


def test_continuity_workflow_runs_no_code_while_monty_is_off(project: AsyncSession) -> None:  # noqa: F811
    """With Monty off, the pass is unchanged and nothing is executed or audited."""
    _place_karl_in_the_river_scene(project)
    prompts: list[str] = []

    def report(prompt: str, _count: int) -> dict[str, Any]:
        """Record the prompt and report nothing."""
        prompts.append(prompt)
        return {"issues": []}

    result, _ = _run("continuity", {}, {"ContinuityReport": report})
    assert result["rules_enabled"] is False and result["rule_findings"] == []
    assert "Exact rule checks" not in prompts[0]
    assert _audits(project) == []


def test_check_continuity_rules_keeps_findings_in_scope(project: AsyncSession, monty_on: None) -> None:  # noqa: F811
    """Findings outside the requested scenes are dropped."""
    _place_karl_in_the_river_scene(project)
    assert len(run_async(check_continuity_rules(project, 1))["findings"]) == 1
    assert run_async(check_continuity_rules(project, 1, [99]))["findings"] == []
