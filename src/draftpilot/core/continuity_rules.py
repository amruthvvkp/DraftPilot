"""Continuity rules as code: exact checks over the script and the Story twin, run in Monty.

Each rule is a small Python function over the read-only ``script`` and ``story`` views
(``core.script_analysis``) that returns findings. All rules run in one audited sandbox execution;
a rule that raises is reported in ``errors`` and the others still run. Findings are advice for the
continuity supervisor and the writer: nothing here writes, and fixes still go through proposals.
The story facts are the typed Story twin records (characters, timeline events, locations) and the
canon knowledge-graph nodes, per the decision not to add parallel fact tables.
"""

from dataclasses import dataclass
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.config import settings
from draftpilot.core.monty import MontyExecutionConfig
from draftpilot.core.script_analysis import run_analysis


@dataclass(frozen=True)
class ContinuityRule:
    """One rule: its function name (the key), the issue kind it reports, what it checks, and its code."""

    key: str
    kind: str
    summary: str
    source: str


_NAMES = '''
def _names(character):
    names = [character["name"], character["cue"] or ""] + character["aliases"]
    out = set()
    for name in names:
        if name:
            out.add(name.upper())
            out.add(name.split()[0].upper())
    return out
'''

RULES: tuple[ContinuityRule, ...] = (
    ContinuityRule(
        "age_drift",
        "timeline",
        "A character's stated ages and the scenes' years imply different birth years.",
        r'''
def age_drift(script, story):
    pattern = r"\b([A-Z][A-Z'.]+(?: [A-Z][A-Z'.]+)?)(?:,| \()\s*(?:now |age |also |AGE )?(\d{1,2})\b(?!'?s)"
    prefixes = ["YOUNG", "YOUNGER", "OLD", "OLDER", "LITTLE", "DR.", "MR.", "MRS.", "MS."]
    births = {}
    for scene in script.scenes:
        if scene["year"] is None:
            continue
        for name, age in re.findall(pattern, scene["action"]):
            parts = [part for part in name.split() if part not in prefixes] or name.split()
            first = parts[0]
            births.setdefault(first, []).append((scene["year"] - int(age), scene["id"], int(age), scene["year"]))
    findings = []
    for name, seen in sorted(births.items()):
        years = [item[0] for item in seen]
        if max(years) - min(years) > 1:
            low = min(seen)
            high = max(seen)
            findings.append({
                "scene_ids": [low[1], high[1]],
                "description": f"{name} is {low[2]} in {low[3]} but {high[2]} in {high[3]}: birth years {low[0]} and {high[0]} disagree.",
                "suggestion": f"Make {name}'s ages consistent with the years, or adjust a scene's year.",
            })
    return findings
''',
    ),
    ContinuityRule(
        "timeline_order",
        "timeline",
        "A character's timeline order disagrees with the events' story-world positions.",
        r'''
def timeline_order(script, story):
    names = {c["id"]: c["name"] for c in story.characters}
    by_character = {}
    for event in story.events:
        if event["chrono_index"] is not None:
            by_character.setdefault(event["character_id"], []).append(event)
    findings = []
    for character_id, events in sorted(by_character.items()):
        events = sorted(events, key=lambda e: e["position"])
        for before, after in zip(events, events[1:]):
            if after["chrono_index"] < before["chrono_index"]:
                findings.append({
                    "scene_ids": [s for s in [before["scene_id"], after["scene_id"]] if s is not None],
                    "description": f"{names.get(character_id, character_id)}: '{after['title']}' follows '{before['title']}' in the timeline but happens earlier in story time.",
                    "suggestion": "Reorder the timeline events or correct their story-time positions.",
                })
    return findings
''',
    ),
    ContinuityRule(
        "event_character_absent",
        "character",
        "A timeline event is placed in a scene where its character neither speaks nor is mentioned.",
        _NAMES
        + r'''
def event_character_absent(script, story):
    scenes = {s["id"]: s for s in script.scenes}
    characters = {c["id"]: c for c in story.characters}
    findings = []
    for event in story.events:
        scene = scenes.get(event["scene_id"])
        character = characters.get(event["character_id"])
        if scene is None or character is None:
            continue
        names = _names(character)
        text = scene["action"].upper()
        if any(name in scene["speakers"] for name in names) or any(name in text for name in names):
            continue
        findings.append({
            "scene_ids": [scene["id"]],
            "description": f"{character['name']}'s event '{event['title']}' is placed in scene {scene['number']} ({scene['heading']}), where {character['name']} does not appear.",
            "suggestion": "Link the event to the scene where it happens, or put the character in this scene.",
        })
    return findings
''',
    ),
    ContinuityRule(
        "after_death",
        "character",
        "A character has timeline events after their death in story time.",
        r'''
def after_death(script, story):
    words = ["dies", "died", "death of", "killed", "is killed", "passes away", "funeral of"]
    names = {c["id"]: c["name"] for c in story.characters}
    findings = []
    for character_id, name in sorted(names.items()):
        events = [e for e in story.events if e["character_id"] == character_id and e["chrono_index"] is not None]
        deaths = [e for e in events if any(w in e["title"].lower() for w in words)]
        if not deaths:
            continue
        death = min(deaths, key=lambda e: e["chrono_index"])
        for event in events:
            if event["chrono_index"] > death["chrono_index"] and event["id"] != death["id"]:
                findings.append({
                    "scene_ids": [s for s in [death["scene_id"], event["scene_id"]] if s is not None],
                    "description": f"{name} has '{event['title']}' after '{death['title']}' in story time.",
                    "suggestion": "If this is a memory, ghost or tall tale, mark it so; otherwise move the event before the death.",
                })
    return findings
''',
    ),
    ContinuityRule(
        "speaker_not_in_cast",
        "character",
        "Someone speaks who is not in the cast (when the cast is kept by hand).",
        _NAMES
        + r'''
def speaker_not_in_cast(script, story):
    known = set()
    for character in story.characters:
        known |= _names(character)
    if not known:
        return []
    missing = {}
    for scene in script.scenes:
        for speaker in scene["speakers"]:
            if speaker not in known:
                missing.setdefault(speaker, []).append(scene["id"])
    return [
        {
            "scene_ids": ids[:10],
            "description": f"{speaker} speaks in {len(ids)} scene(s) but is not in the cast.",
            "suggestion": f"Add {speaker} to the cast, or correct the cue if it is a typo for an existing character.",
        }
        for speaker, ids in sorted(missing.items())
    ]
''',
    ),
    ContinuityRule(
        "location_not_in_story",
        "location",
        "A scene is set somewhere that is not in the story's locations (when locations are kept).",
        r'''
def location_not_in_story(script, story):
    known = set()
    for location in story.locations:
        known.add(location["name"].upper())
        if location["heading_location"]:
            known.add(location["heading_location"].upper())
    if not known:
        return []
    missing = {}
    for scene in script.scenes:
        if scene["location"] and scene["location"] not in known:
            missing.setdefault(scene["location"], []).append(scene["id"])
    return [
        {
            "scene_ids": ids[:10],
            "description": f"{place} is used in {len(ids)} scene(s) but is not one of the story's locations.",
            "suggestion": f"Add {place} to the locations, or correct the heading if it names an existing place.",
        }
        for place, ids in sorted(missing.items())
    ]
''',
    ),
)


# Each rule reports at most this many findings, so one noisy rule cannot crowd out the others.
PER_RULE = 8


def rules_program(rules: tuple[ContinuityRule, ...] = RULES, scene_ids: list[int] | None = None) -> str:
    """Compose the rules into one sandbox program returning ``{"findings": [...], "errors": [...]}``."""
    names = ", ".join(f'("{rule.key}", "{rule.kind}", {rule.key})' for rule in rules)
    scope = repr(sorted(set(scene_ids))) if scene_ids else "None"
    return "\n".join(
        [
            "import re",
            *(rule.source for rule in rules),
            f"_scope = {scope}",
            "findings = []",
            "errors = []",
            f"for key, kind, check in [{names}]:",
            "    try:",
            "        kept = 0",
            "        for finding in check(script, story):",
            "            if _scope is not None and not any(s in _scope for s in finding['scene_ids']):",
            "                continue",
            f"            if kept >= {PER_RULE}:",
            "                break",
            "            finding['rule'] = key",
            "            finding['kind'] = kind",
            "            findings.append(finding)",
            "            kept += 1",
            "    except Exception as exc:",
            "        errors.append(key + ': ' + str(exc))",
            '{"findings": findings, "errors": errors}',
        ]
    )


async def check_continuity_rules(
    session: AsyncSession,
    project_id: int,
    scene_ids: list[int] | None = None,
    *,
    run_id: int | None = None,
    config: MontyExecutionConfig | None = None,
) -> dict[str, Any]:
    """Run every continuity rule once (one audited execution), keeping findings that touch ``scene_ids``."""
    result = await run_analysis(
        session, project_id, rules_program(RULES, scene_ids), run_id=run_id, config=config, purpose="continuity_rules"
    )
    value: dict[str, Any] = result.value
    return {"rules": [rule.key for rule in RULES], **value, "duration_ms": result.duration_ms}


def continuity_rules_enabled() -> bool:
    """Return whether rules may run: Monty itself is switched on."""
    return settings.monty.enabled
