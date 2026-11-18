---
icon: lucide/box
---

# Code mode and the Monty sandbox

!!! note "Experimental, and off by default"
    Code mode only runs when you set `MONTY__ENABLED=true`. With it off, the room works exactly as
    before and no code is run. You can leave it off and lose nothing.

## What it is for

Some questions about a script have one exact answer: how many scenes are set at night, what share of
the dialogue is Edward's, which scenes a character speaks in, whether a character's ages agree with the
years in the headings. A model reading scenes one by one gets these wrong or spends many tool calls on
them. In **code mode**, a room role writes one short Python snippet instead, and DraftPilot runs it in
Pydantic Monty (the `pydantic-monty` package), a minimal Python interpreter that can't reach anything
outside itself.

Code mode can only read. Any change it leads to is still a proposal that you approve or reject.

## What uses it

- **Code-mode roles.** The showrunner, researcher, continuity supervisor, story editor and twin keeper
  get two extra tools while Monty is on: `analyze_script` (run a snippet) and `check_continuity_rules`.
  The other roles never see them.
- **The continuity pass.** The `continuity` room workflow first runs the built-in continuity rules
  (below), then hands their findings to the continuity supervisor, who confirms the real ones, dismisses
  the intentional ones and looks for what rules can't see. The run's result lists the rule findings
  separately (`rule_findings`).
- **You and external agents.** `POST /api/v1/projects/{id}/analyze-script` with `{"code": "..."}`, and
  `POST /api/v1/projects/{id}/continuity-rules` with `{"scene_ids": [...]}` (empty means all). Over MCP
  the same two tools are available, but external clients also need `MCP__ENABLE_CODE_TOOLS=true` and
  the `script.analyze` grant on the project ([MCP integration](mcp.md)).

## What the code sees

The snippet's last expression is its result. It gets two read-only objects and nothing else:

| Object | Data | Methods |
|---|---|---|
| `script` | `title`; `scenes` in script order, each with `id`, `number`, `act`, `heading`, `int_ext`, `location`, `time`, `year` (from a `(1973)` in the heading), `words`, `action_words`, `dialogue_words`, `speakers`, `speaker_words`, `speaker_lines`, `action` (the action text) | `summary()`, `scene(id)`, `dialogue_share(by="words" or "lines")`, `pacing_curve()`, `scene_character_matrix(top=0)`, `character_scenes(name)` |
| `story` | `title`, `logline`, `characters`, `relationships`, `events` (character timeline events), `locations`, `beats`, `facts` (canon graph nodes) | `character(name)` (by name, cue or alias), `events_for(name)` |

For example, the night scenes and Edward's share of the dialogue:

```python
night = [s["number"] for s in script.scenes if s["time"] == "NIGHT"]
{"night_scenes": len(night), "edward": script.dialogue_share()["EDWARD"]}
```

On *Big Fish* this returns `{"night_scenes": 50, "edward": 0.454}`, out of 191 scenes.

## Continuity rules

The rules are written as code and run in the sandbox, all in one audited execution. They work over
the script and the Story twin's typed records (characters, timeline events, locations) and the canon
graph. There are no separate fact tables. Each rule reports at most eight findings, and a rule that
fails is listed in `errors` while the others still run.

| Rule | Kind | Flags |
|---|---|---|
| `age_drift` | timeline | stated ages (`WILL, now 28`, `KARL (30)`) that imply different birth years given the scenes' years |
| `timeline_order` | timeline | a character's timeline order that disagrees with the events' story-time positions |
| `event_character_absent` | character | a timeline event placed in a scene where its character neither speaks nor is mentioned |
| `after_death` | character | events after a character's death in story time (flashbacks and ghosts are fine, so check them) |
| `speaker_not_in_cast` | character | someone speaking who isn't in the cast |
| `location_not_in_story` | location | a scene set somewhere that isn't one of the story's locations |

Findings are exact, but they aren't judgements. A non-linear story can break `timeline_order` on
purpose, and that's for you or the continuity supervisor to decide.

## Settings

| Setting | Default | What it limits |
|---|---|---|
| `MONTY__ENABLED` | `false` | whether any code may run at all |
| `MONTY__MAX_CODE_CHARS` | `20000` | the length of the code |
| `MONTY__MAX_INPUT_ITEMS` | `100` | how many named inputs it may receive |
| `MONTY__MAX_DURATION_SECONDS` | `0.5` | how long one execution may run (sandbox time; host calls don't count) |
| `MONTY__MAX_OUTPUT_CHARS` | `20000` | how much printed output, and how large a result, it may produce |
| `MONTY__MAX_MEMORY_MB` | `64` | the heap of one execution |
| `MCP__ENABLE_CODE_TOOLS` | `false` | whether external MCP clients may call the code tools |

With Monty off, a direct call fails with "Monty execution is disabled" and is still audited. The
continuity pass doesn't attempt a run at all, so it leaves no audit record. Approve a policy for who
may run what before you enable Monty on a shared installation.

## Security limits

- No external lookups, filesystem mounts, OS callbacks, network clients, shell or process access.
  The code sees only the two views above, exposed through `pydantic_monty.ClassInstance` allow-lists:
  their public data and the listed methods. Private methods are refused.
- The views are snapshots taken before the run. Data crosses into the sandbox by value, so changing
  it inside the sandbox changes nothing outside, and no method writes.
- Code that is empty or too long, or that receives too many inputs, is refused before it runs.
- Execution runs in Monty's worker process with time and memory limits; output beyond the limit
  stops the run.
- When named inputs are present, Monty's static type check is skipped (those names only exist at run
  time). The interpreter boundary and the resource limits still apply.

## The audit log

Every attempt, successful or not, writes an audit record to the project: its status, a SHA-256 hash
of the code, the number of inputs, the size of the output, the duration, the workflow run id (when a
room run made the call) and a shortened error message. **The code and the input values are never
stored.** The sandbox's own error, such as a `NameError`, is returned to the caller so a model can fix
its code, but it isn't stored, because it can quote the code. Every execution is also a Logfire span
(`monty {purpose}`) carrying the code hash, project, run and status.

Read the records for a project:

```text
GET /api/v1/projects/{project_id}/monty-executions
```

Over MCP, the `read_monty_executions` tool returns the same redacted records. It needs the
`monty.audit.read` grant on that project ([MCP integration](mcp.md)).

## For developers

- `core/monty.py`: `execute_glue_audited` is the one entry point. It runs the code off the event loop,
  writes the audit record through the project-scoped CRUD layer (on success and on failure) and opens
  the span. `host=` passes host functions (Monty's `external_lookup`), and `inputs` may hold
  `ClassInstance` wrappers. `execute_glue` writes no audit and is only for isolated unit tests.
- `core/script_analysis.py`: `ScriptView`/`StoryView`, their loaders, `host_objects` (the
  allow-lists) and `analyze_script`. To give code a new statistic, add a method to a view, then add
  it to `SCRIPT_METHODS` or `STORY_METHODS`.
- `core/continuity_rules.py`: `RULES`. A rule is a function in Monty-compatible Python, named by its
  key, that takes `(script, story)` and returns findings (`scene_ids`, `description`, `suggestion`).
  `rules_program` composes them into one program.
- Roles opt in with `code_mode: true` in their spec (`agents/specs/*.yaml`). `agents/runtime.py` offers
  `CODE_TOOLS` only when `code_mode_active` (a code-mode role, tools on, `RoomDeps.code_mode`, and
  Monty on) and adds the code-mode instructions to that run.
- Durable runs execute Monty only inside activities, never in workflow code. The continuity
  pass's rule step (`room_continuity_rules`) is behind `workflow.patched("continuity-rules-as-code")`,
  so runs recorded before it still replay.
- Tests: `tests/test_code_mode.py` (exact Big Fish stats, sandbox escapes and limits, rules, audits,
  gating, the workflow). Eval: `uv run python -m draftpilot.evals code_mode` compares code mode with
  plain tool calls on exact questions (accuracy, tool calls, duration).
- Not built yet: Pydantic AI Harness `CodeMode`/`DynamicWorkflow`. `pydantic-ai-harness` pins
  `pydantic-ai-slim` 2.62 and DraftPilot is on 2.51, so code mode is built directly on `pydantic-monty`
  for now. A shared worker pool (`MONTY__POOL_SIZE`) is also left for later: each execution starts its
  own Monty worker.
