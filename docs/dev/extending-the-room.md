# Extending the room

## Add a role

1. Create `src/draftpilot/agents/specs/<key>.yaml`:

   ```yaml
   key: dialogue_coach
   label: Dialogue coach
   description: Sharpen voice, subtext and rhythm in dialogue.
   temperature: 0.6
   thinking: true          # false for graders: faster, and they judge rather than create
   instructions: |
     You are the dialogue coach of a professional writers' room...
   ```

2. Add the key to `AgentRoleKey` and `AGENT_ROLES` in `core/agent_roles.py`. A test checks that the
   catalogue and the specs stay in step.
3. To let the showrunner consult the role, add it to `SPECIALISTS` in `agents/runtime.py` and list it
   in `specs/showrunner.yaml`.

## Add a workflow

Workflows are Temporal workflows in `agents/room_workflows.py`. Their typed outputs, parameters,
database activities and catalogue live in `agents/workflows.py`. To add one:

1. Define a typed output (a `BaseModel`) for each step, and a params model for the workflow.
2. Subclass `RoomWorkflowBase` with `@workflow.defn(name="room:<key>")` and a `key`. Its
   `@workflow.run` returns `await self.execute(run, Params, self.body)`.
3. Write `body` as plain Python:
   - each step is `await self.consult(step, role, prompt, OutputType)`. Pass `tools=False` when
     the prompt already contains everything the role needs, which makes the step faster and stops
     the role from wandering around the project;
   - draft-critique loops are `while` loops;
   - fan-outs are `asyncio.gather(...)`.
4. Workflow code must be deterministic. Every database read or write is an `@activity.defn` in
   `agents/workflows.py`, called with `await self.activity(fn, ...)` and listed in `ROOM_ACTIVITIES`.
   Don't read clocks, randomness or the network in `body`.
5. End generative workflows in an activity that creates `AgentProposal`s. Reports just return data.
6. Register a `RoomWorkflow` in `ROOM_WORKFLOWS` and the class in `ROOM_WORKFLOW_CLASSES`. The API,
   MCP tools, launcher form and run views pick it up automatically.
7. Test it with a scripted `FunctionModel` (see `tests/test_room_workflows.py`). `run_room_workflow`
   runs it on an embedded Temporal test server. Add a scenario to `tests/test_temporal_replay.py`,
   re-record with `TEMPORAL_RECORD=1`, and add online checks in `evals/online.py` and an eval suite
   in `evals/suites.py`.

**Changing an existing workflow:** the replay tests (`tests/test_temporal_replay.py`) must pass
against the committed histories in `tests/temporal_histories/`. A change that would break an
in-flight run has to go behind `workflow.patched("<change-id>")` so that old histories take the old
path. Only re-record the histories when every run started on the old code has finished.

## Add a pipeline stage

`room:develop_story` (`DevelopStory` in `agents/room_workflows.py`) runs the stages listed in
`PIPELINE_STAGES`, each gated on the writer. To add one:

1. Add the stage name to `PipelineStage` and `PIPELINE_STAGES` in `agents/workflows.py`, in pipeline
   order, plus any parameter it needs on `DevelopStoryParams`.
2. In `DevelopStory.body`, consult the role(s) for the stage, create its proposals with an activity,
   then `await self._checkpoint("<stage>", ids, params)`. The checkpoint waits for a
   `proposal_decided` signal per proposal (sent by the proposals service after the writer decides)
   and refreshes the story context, so the next stage builds only on what was approved.
3. Put the new code behind `workflow.patched("<change-id>")` and pass the replay tests: runs already
   waiting at a checkpoint must replay unchanged.

## Add an MCP tool

Story and studio tools live in `mcp/studio_tools.py`; older project, screenplay and run tools are in
`mcp/server.py`. Add an `@mcp.tool` that calls `authorize_invocation(...)` with a capability from
`core/capabilities.py`, and call the shared service in `core/` rather than an `api.*` module. Mark
mutating capabilities `approval_required=True` unless their result is only a proposal.

- **In-app agents:** add the tool to `READ_TOOLS`, `PROPOSE_TOOLS` or `APPROVAL_TOOLS` (which feeds
  `EDIT_TOOLS`) in `agents/runtime.py`. `tools_for_mode` maps the chat's permission modes onto these
  sets: `chat_only` reads, `suggest` reads and proposes, `project_edit` also gets the approval-gated
  tools, which the chat defers to an in-chat approval card.
- **REST parity:** a new REST route must be mapped to its MCP tool (or an explicit exemption) in
  `PARITY` in `tests/test_mcp_studio.py`; the test fails otherwise.
- **Docs:** add the tool to the reference in [MCP integration](../mcp.md).

## Add an eval suite

Add a builder to `evals/suites.py` that returns `(Dataset, task)`, and register it in `SUITES`. Use
deterministic evaluators from `evals/evaluators.py` wherever possible, and an `LLMJudge` for what
they can't check. Run the suite, then record its baseline:

```bash
uv run python -m draftpilot.evals <suite> --save-baseline
```
