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

Workflows are `pydantic_graph` graphs in `agents/workflows.py`. The steps are:

1. Define a typed output (a `BaseModel`) for each step, and a params model for the workflow.
2. Build the graph from steps that call `consult(ctx, step, role, prompt, OutputType)`. Pass
   `tools=False` when the prompt already contains everything the role needs, which makes the step
   faster and stops the role from wandering around the project.
3. Use the builder's primitives:
   - `_loop_decision(...)` for draft-critique loops;
   - `g.edge_from(step).map().to(...)` with `g.join(reduce_list_append, ...)` to fan out in
     parallel.
4. End generative workflows in a gate that creates `AgentProposal`s. Reports just return data.
5. Register a `RoomWorkflow` in `ROOM_WORKFLOWS`. The API, MCP tools, launcher form and run views
   pick it up automatically.
6. Test it with a scripted `FunctionModel` (see `tests/test_room_workflows.py`). Add online checks in
   `evals/online.py` and an eval suite in `evals/suites.py`.

## Add an MCP tool

Add an `@mcp.tool` in `mcp/server.py` that calls `authorize_invocation(...)` with a capability from
`core/capabilities.py`. Mark mutating capabilities `approval_required=True` unless their result is
only a proposal. To give in-app agents the tool, add it to `READ_TOOLS`, `PROPOSE_TOOLS` or
`EDIT_TOOLS` in `agents/runtime.py`.

## Add an eval suite

Add a builder to `evals/suites.py` that returns `(Dataset, task)`, and register it in `SUITES`. Use
deterministic evaluators from `evals/evaluators.py` wherever possible, and an `LLMJudge` for what
they can't check. Run the suite, then record its baseline:

```bash
uv run python -m draftpilot.evals <suite> --save-baseline
```
