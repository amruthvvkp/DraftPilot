# MCP integration

DraftPilot's MCP server is the one tool surface for its own agents and for external ones such as
Claude (Desktop, Code), ChatGPT and other MCP clients. Everything a writer can do in the studio —
from the first idea to a finished draft — is available as a tool: projects, the storyline,
characters with their motives, objectives, relationships and timelines, locations, the outline
(acts and beats), scenes and screenplay blocks, revisions, imports and exports, proposals, the canon
graph, artifacts, the writers' room workflows and both twins.

## Connect a client

| Transport | Start it | Identity |
|---|---|---|
| stdio (a local process) | `uv run python -m draftpilot.mcp` | `MCP__STDIO_CLIENT_ID` (default `mcp-stdio`) |
| Streamable HTTP | the `mcp` Compose service on `http://localhost:9001/mcp` | the bearer token: `MCP__AUTH_TOKEN`, or one of `MCP__CLIENT_TOKENS` |

Claude Code, for example:

```bash
claude mcp add draftpilot -- uv --directory /path/to/DraftPilot run python -m draftpilot.mcp
```

or, over HTTP:

```bash
claude mcp add --transport http draftpilot http://localhost:9001/mcp --header "Authorization: Bearer draftpilot-local-token"
```

### Trust the client

A client can do nothing until the installation grants it capabilities. Register it once and grant
it capabilities on one project, or installation-wide (a grant without a project covers every
project, and is required to list and create projects). Both use the admin token:

```bash
curl -X POST localhost:9000/api/v1/mcp/clients -H "Authorization: Bearer $MCP__ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d '{"client_id": "mcp-stdio", "name": "Claude Code"}'
curl -X POST localhost:9000/api/v1/mcp/grants -H "Authorization: Bearer $MCP__ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d '{"client_id": "mcp-stdio", "capabilities": ["*"]}'
```

Granting a capability never skips the writer: writes marked `approval_required` still need a
writer-decided approval for each call (below).

## Develop a screenplay over MCP

Five prompts walk an agent through the guided flow, each built on the tools below:
`develop_storyline`, `develop_characters`, `build_outline`, `draft_script` and `review_script`.
A typical session:

1. `create_project` (or `list_projects`), then `read_story_context`, the compact brief every
   DraftPilot agent receives.
2. Storyline: `read_storyline`, then `update_project(fields={"logline", "premise", "synopsis",
   "theme", "tone", ...})` or `propose_story_change(kind="storyline", action="update")`.
3. Cast: `create_story_entity` / `update_story_entity` / `delete_story_entity` with
   `kind="character" | "relationship" | "timeline_event" | "location"`, read back with
   `list_story_entities` and `read_character` (profile, timeline and relationships together).
4. Outline: `create_act` / `update_act` / `delete_act`, beats via `kind="beat"`, or a whole outline at
   once with `propose_outline`; read it with `read_outline` (acts → beats → scene headings).
5. Script: `create_scene(heading, fountain=...)`, `write_scene` (replace a scene from Fountain),
   `move_scene`, `delete_scene`, and block-level `create_block` / `update_block` / `delete_block` /
   `reorder_blocks`; read with `read_screenplay_scenes`.
6. Review: `snapshot_scene`, `diff_scene_revisions`, `restore_scene_revision`; `start_room_workflow`
   for coverage, continuity, rewrites and the audience panel; `render_screenplay_export`.

Every write takes the `expected_version` you last read and fails with a conflict if the writer
changed the target since.

### Tool reference

| Area | Tools |
|---|---|
| Projects | `list_projects`, `create_project`, `update_project`, `duplicate_project`, `delete_project`, `write_reference`, `read_project_overview` |
| Story | `read_storyline`, `read_story_context`, `list_story_entities`, `read_character`, `read_outline`, `create_story_entity`, `update_story_entity`, `delete_story_entity`, `propose_story_change`, `propose_outline`, `apply_story_operation`, `read_project_artifacts`, `write_artifact` |
| Structure and script | `create_act`, `update_act`, `delete_act`, `create_scene`, `write_scene`, `update_scene`, `move_scene`, `delete_scene`, `create_block`, `update_block`, `delete_block`, `reorder_blocks`, `read_screenplay_scenes`, `read_dialogue_translations`, `propose_dialogue_translation` |
| Proposals | `list_proposals`, `propose_screenplay_change`, `review_screenplay_proposal`, `reject_proposal`, `propose_timeline_reorder`, `review_timeline_proposal`, `reject_timeline_proposal` |
| Revisions, import and export | `snapshot_scene`, `read_scene_revisions`, `diff_scene_revisions`, `restore_scene_revision`, `import_screenplay`, `render_screenplay_export`, `create_screenplay_export`, `list_project_backups`, `create_project_backup`, `restore_project_backup` |
| Canon, twins and search | `read_story_twin`, `refresh_story_twin_now`, `write_canon_node`, `write_canon_edge`, `read_writer_twin`, `update_writer_profile`, `remember_writer_preference`, `retrieve_project_context`, `reindex_project_search` |
| Room and runs | `list_room_workflows`, `start_room_workflow`, `start_context_workflow`, `apply_context_workflow`, `start_evaluation`, `read_project_evaluations`, `read_workflow_run`, `control_workflow_run`, `read_monty_executions` |

Resources: `draftpilot://capabilities`, `draftpilot://schemas/context`, `draftpilot://context-workflows`,
and per project `.../storyline`, `.../characters`, `.../outline`, `.../locations`, `.../timeline`,
`.../artifacts`, `.../context` and `.../knowledge-graph`. A parity test
(`tests/test_mcp_studio.py`) fails when a REST operation has no MCP tool or documented exemption.

## Writer approval for external writes

An MCP client can never approve its own writes. Capabilities marked `approval_required` in
`draftpilot://capabilities` (project edits and deletes, story and structure writes, story operations,
applying context, approving, rejecting or rolling back proposals, restores, exports, backups, canon,
artifact and writer-twin writes, run control) go through these steps:

1. **First call.** The client calls the tool without `approval_id`. DraftPilot checks the grant and
   records a pending approval request, and the call fails with a message such as
   `Writer approval is required: approval request 12 is pending … retry with approval_id=12`.
   Nothing changes yet.
2. **Writer decides.** The request appears under *External agent requests* in the project workspace.
   There the writer sees the client, capability and arguments, and chooses **Approve request** or
   **Reject**. The REST equivalents are `GET/POST /api/v1/projects/{id}/mcp-approvals[/{approval_id}/approve|reject]`.
3. **Retry.** The client repeats the call with `approval_id=12`. The approval is bound to the client,
   project, capability, action and a SHA-256 digest of the **full call arguments**. It is used once,
   and it expires after `MCP__APPROVAL_TTL_SECONDS` (default 900). A changed argument, a replay, or a
   pending, rejected or expired request is refused and audited.

Creating proposals (`propose_story_change`, `propose_outline`, `propose_screenplay_change`,
`propose_timeline_reorder`, `propose_dialogue_translation`) needs no pre-approval, because a proposal
changes nothing until the writer reviews it. Creating a project, snapshotting a scene, importing a
draft and refreshing the Story twin are not destructive and need no approval either.

## External client smoke check

The repository includes a portable smoke check for the authenticated client path. With the
Compose stack running and a project-scoped `outline.read` grant for the default local client:

```bash
UV_CACHE_DIR=/private/tmp/draftpilot-uv-cache uv run python scripts/mcp_smoke.py
# tools=70 resources=3 artifact_type=dict tool_type=dict
```

Set `DRAFTPILOT_MCP_ENDPOINT`, `DRAFTPILOT_MCP_TOKEN`, and `DRAFTPILOT_MCP_RESOURCE` to target
another compatible Streamable HTTP server. The client validates endpoints, applies timeouts, and
bounds response sizes before returning data.

DraftPilot exposes a typed MCP boundary from the `mcp` Compose service. The discoverable
`draftpilot://capabilities` resource lists the current capability names, scopes, and whether a
mutation requires writer approval. The `workflow_turn` prompt carries page, artifact, and selection
scope without exposing credentials. `propose_timeline_reorder` persists a project/screenplay-scoped
reversible proposal after checking the server-authoritative current order. `review_timeline_proposal`
applies or rolls it back only with the matching grant and explicit writer approval.

Discoverable project resources include `draftpilot://projects/{project_id}/artifacts` for canonical
story artifacts and `draftpilot://projects/{project_id}/context` for the project, artifacts, and
knowledge-graph context envelope. Both are project-authorized, audited, and output-bounded.

The `retrieve_project_context` tool uses the server-side RAG service and returns project-scoped
results with source identifiers and content versions. Clients can inspect the response contract at
`draftpilot://schemas/context`; clients never receive vector-store credentials or direct database
access. Retrieval requires the `context.read` grant for the requested project and is bounded by the
MCP request timeout and output limit.

The static `draftpilot://context-workflows` resource and `start_context_workflow` tool expose the
same context-generation catalog and durable run contract used by the React context page. The tool
requires `context.generate`, validates the source artifact kind against the selected workflow, and
returns a queued `context_generation` run; the worker produces a cited review-only suggestion and
never changes canonical context without a later typed, approved operation.

`apply_context_workflow` is the explicit approval path for that operation. It creates a
provenance-linked knowledge-graph node, requires `context.apply` plus a writer-approved `approval_id` (see above), rejects
duplicate application and stale source versions, refreshes RAG, and uses the same run state as the
REST path.

`read_project_artifacts` and `read_screenplay_scenes` expose canonical editable artifacts and
ordered screenplay blocks through the same project authorization boundary. Both tools enforce the
configured response-size limit, and screenplay reads reject a screenplay belonging to another
project.

`apply_story_operation` and `POST /api/v1/projects/{project_id}/artifacts/{artifact_id}/operations`
share the typed story-operation service. Supported operations are `set_logline` for briefs,
`add_beat` for outlines/timelines, `add_character_arc` for character artifacts, and
`add_canon_rule` for canon artifacts. Operations are versioned, appended to artifact metadata,
mark downstream artifacts stale, and trigger an incremental RAG refresh; MCP use additionally
requires the `story.operation` grant and explicit approval.

`propose_screenplay_change` accepts typed scene `heading`/`body` operations or semantic-block
`element_type`/text/layout operations when `block_id` is supplied. To rewrite a whole scene, pass
`operation={"fountain": "<the scene in Fountain>"}` without a `block_id`: the text is parsed into
typed blocks, and approval replaces the scene's blocks in place (ids stay stable, authorship becomes
`proposal:<id>`), while rollback restores the exact prior blocks. It stores a reviewable agent
proposal using the scene's current server-derived version. It never applies the operation;
approval and optimistic-concurrency checks remain on the DraftPilot approval boundary. External
clients use `review_screenplay_proposal` to approve or roll back the same proposal records; it
delegates to the REST application logic rather than opening a second mutation path.

Timeline reorders follow the same reversible lifecycle: `propose_timeline_reorder` creates a
pending order with cumulative timings, approval applies it, and rollback restores the original
order when the approved order is still current.

`read_dialogue_translations` exposes linked variants for a dialogue block while retaining the
source version. `propose_dialogue_translation` is approval-gated and stores a typed proposal rather
than changing source dialogue. `read_scene_revisions` exposes immutable scene snapshots for external
diff and rollback planning. `render_screenplay_export` renders bounded Fountain, FDX, HTML, or PDF
content (PDF is returned as base64),
and `create_screenplay_export` persists an approved, checksummed export beneath the configured
backup volume without changing canonical screenplay data.
`read_monty_executions` exposes only project-authorized, redacted Monty audit fields; generated
source code and input values are never returned.
`list_project_backups` lists validated backup manifests, `create_project_backup` creates an approved
archive, `restore_project_backup` restores it into a new project, and `read_workflow_run` reads
durable run state. Backup creation and restore require both the project grant and a writer-approved
`approval_id`; they never overwrite the source project.

`control_workflow_run` exposes explicit `resume` and `cancel` actions. It requires the client grant
for `runs.control` and a writer-approved `approval_id`; every attempt is audited, and resume
restarts the same durable run rather than creating a second run.

External clients should receive a project/client grant before invoking capabilities. The server must
validate both scopes and approval state; a UI permission is never authoritative. Credentials belong
in the server environment or encrypted storage and must not be sent to an MCP client. Streamable HTTP
is available on `http://localhost:9001` in local Compose; configure the client for the server's MCP
endpoint rather than the root health URL.

Client registration and grant administration are protected separately from MCP invocation with
`Authorization: Bearer <MCP__ADMIN_TOKEN>`. Keep this token server-side and use a distinct value from
`MCP__AUTH_TOKEN`; the local default is only for development.
Grant creation also validates the capability against the server catalog, so arbitrary database or
unregistered tool permissions cannot be persisted.

Copilot runs carry one of `chat_only`, `suggest`, `scoped_edit`, or `project_edit`. The server
rejects proposals originating from `chat_only` runs; other modes still create typed proposals for
the writer approval/diff/rollback lifecycle. A `scoped_edit` run must carry a server-defined target
kind, target id, and optional scene id in its persisted run envelope; proposal creation and approval
reject targets outside that scope. `project_edit` is project-wide. Approval endpoints re-check the
originating run so a client cannot bypass the stored permission mode.
Administrators can revoke a project grant with `DELETE /api/v1/mcp/projects/{project_id}/grants/{grant_id}`;
the endpoint is project-scoped and does not expose client bearer tokens.

The Streamable HTTP transport requires `Authorization: Bearer <MCP__AUTH_TOKEN>`. Compose uses
`draftpilot-local-token` for local development; replace it before exposing port 9001 outside the
local machine. For multiple external clients, set `MCP__CLIENT_TOKENS` to a JSON map of registered
client ids to distinct bearer tokens; those identities are used for project grants and audit events.
Local stdio transport is available for a process launched by the same user and does
not need an HTTP bearer header. Start it with `uv run python -m draftpilot.mcp`; the process
speaks MCP on stdin/stdout with the human-readable FastMCP banner disabled.
Its project scope is still server-authoritative: register a client whose id matches
`MCP__STDIO_CLIENT_ID` (default `mcp-stdio`) and grant it only the required capabilities.

Mutation tools are added only through the same capability service, with audit records, redaction,
timeouts, output limits, and explicit consent. Project evaluations are available through the
`read_project_evaluations` tool, while deterministic evaluation runs persist through the same
durable workflow-run service.

The durable run API currently supports `GET` inspection, `POST /resume`, and `POST /cancel` under
`/api/v1/projects/{project_id}/runs/{run_id}`. Every run executes as a Temporal workflow, so it
survives worker restarts and browser disconnects; cancellation cancels the workflow and keeps the
run's history. Run responses also expose `attempt_count` and `max_attempts`: Temporal retries the
run's activity until that budget is exhausted, and the final failure is durable and can be explicitly
resumed by an authorized client.
REST run creation accepts `max_attempts` from 1 through 10 for workflow, evaluation, and context
runs; omitted values use the default of three.

Copilot turns are persisted at `/api/v1/projects/{project_id}/copilot/messages`. Each message
records its page, artifact, selection, instruction layers, retrieved citations, and active typed
tools so a reconnecting client can restore context without direct database access.

The `/copilot/messages/respond` endpoint persists the user turn, invokes the configured server-side
PydanticAI provider, and persists the assistant reply. If `LLM__ENABLED` is false or the provider is
unavailable, it returns `503` after retaining the user turn; the UI does not fabricate a response.
The React rail uses `/copilot/messages/respond-async`: it returns the persisted user message and a
workflow run, polls the project-scoped run endpoint, and reloads messages after worker completion.
The run stores the full instruction, citation, tool, page, artifact, and selection envelope, keeping
the turn recoverable after a browser disconnect or worker restart.

Canonical graph data is discoverable at `draftpilot://projects/{project_id}/knowledge-graph` and
requires the `knowledge_graph.read` project grant. The resource returns only nodes and edges for
the requested project and records the invocation in the redacted MCP audit log.

DraftPilot also provides the `DraftPilotMCPClient` outbound adapter for built-in agents and
workflow integrations. It supports authenticated Streamable HTTP (`list_tools` and `call_tool`)
with prompt/resource discovery and retrieval (`list_prompts`, `get_prompt`, `list_resources`, and
`read_resource`), plus explicitly configured local stdio (`call_stdio_tool`). HTTP endpoints reject embedded
credentials, cloud metadata targets, private/link-local/reserved IP literals or DNS results, and
multicast addresses; loopback endpoints remain available for local-first services. Hostnames must
resolve before a session is opened. Responses are bounded by the configured output limit. External
MCP results must still be translated into typed DraftPilot operations before any project mutation;
the client never receives database credentials or a database connection.

## Writers' room workflows

`list_room_workflows` returns every room workflow with its parameter JSON schema, and
`start_room_workflow(project_id, workflow, params)` starts one as a durable run (capability
`room.workflow`; follow it with `read_workflow_run`). Generative workflows end in proposals the writer
reviews; analytic ones end in a report on the run. See [Writers' room](writers-room.md).
