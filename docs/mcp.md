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
| stdio (a local process) | `uvx draftpilot-mcp` ([installed package](install.md#draftpilot-mcp)), or `uv run draftpilot mcp` from a checkout | `MCP__STDIO_CLIENT_ID` (default `mcp-stdio`) |
| Streamable HTTP | the `mcp` Compose service on `http://localhost:9001/mcp`, or `draftpilot-mcp serve --http` | the bearer token: `MCP__AUTH_TOKEN`, or one of `MCP__CLIENT_TOKENS` |

`draftpilot-mcp config <client>` prints the exact snippet for Claude Code, Claude Desktop, Cursor or HTTP.
Claude Code, for example:

```bash
claude mcp add draftpilot -- uvx draftpilot-mcp
```

or, from a checkout:

```bash
claude mcp add draftpilot -- uv --directory /path/to/DraftPilot run draftpilot mcp
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
   A timeline event also carries `motivation`, `history`, `intensity` (−5 a low … +5 a high) and
   `chrono_index` (a sortable story-world position; `story_time` is its label).
4. Journey map: `kind="moment"` is a moment several characters share (`title`, `summary`,
   `chrono_index`, `story_time`, `scene_id`, `beat_id`); link each participant's event to it with
   `moment_id`, and list them with `list_story_entities(kind="timeline_event", moment_id=...)`.
   `kind="variant"` saves a named scene order (`name`, `scene_ids`) without applying it. Agents may
   propose moments with `propose_story_change(kind="moment")`; variants stay the writer's.
5. Outline: `create_act` / `update_act` / `delete_act`, beats via `kind="beat"`, or a whole outline at
   once with `propose_outline`; read it with `read_outline` (acts → beats → scene headings).
6. Script: `create_scene(heading, fountain=...)`, `write_scene` (replace a scene from Fountain),
   `write_scene_content` (save a scene's blocks in one write: blocks that keep their `id` are
   updated, blocks without one are created, missing ones are deleted, and the scene version bumps
   once), `move_scene`, `delete_scene`, and block-level `create_block` / `update_block` /
   `delete_block` / `reorder_blocks`; read with `read_screenplay_scenes`.
7. Review: `snapshot_scene`, `diff_scene_revisions`, `restore_scene_revision`; `start_room_workflow`
   for coverage, continuity, rewrites and the audience panel; `render_screenplay_export`.

Every write takes the `expected_version` you last read and fails with a conflict if the writer
changed the target since.

### Tool reference

| Area | Tools |
|---|---|
| Projects | `list_projects`, `create_project`, `update_project`, `duplicate_project`, `delete_project`, `write_reference`, `read_project_overview` |
| Story | `read_storyline`, `read_story_context`, `list_story_entities`, `read_character`, `read_outline`, `create_story_entity`, `update_story_entity`, `delete_story_entity`, `propose_story_change`, `propose_outline`, `apply_story_operation`, `read_project_artifacts`, `write_artifact` |
| Structure and script | `create_act`, `update_act`, `delete_act`, `create_scene`, `write_scene`, `write_scene_content`, `update_scene`, `move_scene`, `delete_scene`, `create_block`, `update_block`, `delete_block`, `reorder_blocks`, `read_screenplay_scenes`, `read_dialogue_translations`, `propose_dialogue_translation` |
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
2. **Writer decides.** The request appears under **External agent requests** in the Script workspace's context rail.
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

## Security model

- **Grants.** Every client needs a project (or installation-wide) grant for each capability it
  calls. The server checks the grant and approval state on every call; a UI permission is never
  authoritative. Grant creation validates the capability against the server catalog, so unknown
  tools or database permissions can't be granted. Revoke a project grant with
  `DELETE /api/v1/mcp/projects/{project_id}/grants/{grant_id}`; it never exposes client tokens.
- **Tokens.** Streamable HTTP requires `Authorization: Bearer <MCP__AUTH_TOKEN>`. Compose uses
  `draftpilot-local-token` for development; replace it before exposing port 9001 beyond your
  machine. For several clients, set `MCP__CLIENT_TOKENS` to a JSON map of client ids to distinct
  tokens; those ids are used for grants and audit events. Point clients at the `/mcp` endpoint,
  not the root health URL.
- **Administration.** Client registration and grants are protected separately, with
  `Authorization: Bearer <MCP__ADMIN_TOKEN>`. Keep it server-side and different from
  `MCP__AUTH_TOKEN`.
- **stdio.** A local process launched by the same user needs no bearer header, but its scope is
  still server-authoritative: register a client whose id matches `MCP__STDIO_CLIENT_ID` and grant it
  only what it needs. The FastMCP banner is disabled so stdout stays pure MCP.
- **Limits.** Every tool is audited and redacted, and bounded by the MCP request timeout and output
  limit. Credentials stay in the server environment or encrypted storage and are never sent to a
  client.

## Tool notes

### Context and retrieval

- `draftpilot://capabilities` lists every capability with its scope and whether it needs writer
  approval. The `workflow_turn` prompt carries page, artifact and selection scope without
  credentials.
- `draftpilot://projects/{project_id}/artifacts` and `…/context` return the project's artifacts and
  its full context envelope; `…/knowledge-graph` returns the canon graph (grant
  `knowledge_graph.read`). All are project-authorized, audited and output-bounded.
- `retrieve_project_context` searches the project through the RAG service and returns results with
  source ids and content versions (grant `context.read`; contract at `draftpilot://schemas/context`).
  Clients never get vector-store credentials or database access.
- `read_project_artifacts` and `read_screenplay_scenes` return editable artifacts and ordered
  screenplay blocks; a screenplay from another project is refused.

### Context workflows

`draftpilot://context-workflows` and `start_context_workflow` expose the same catalog and durable
run as the studio's [context workflows](context-workflows.md) (grant `context.generate`). The worker
produces a cited, review-only suggestion. `apply_context_workflow` applies it as a
provenance-linked canon node; it needs `context.apply` and a writer-approved `approval_id`, and it
refuses duplicate application and stale source versions.

### Screenplay proposals

`propose_screenplay_change` accepts typed scene `heading`/`body` operations, or block
`element_type`/text/layout operations when `block_id` is given. To rewrite a whole scene, pass
`operation={"fountain": "<the scene in Fountain>"}` without a `block_id`: approval replaces the
scene's blocks in place (ids stay stable, authorship becomes `proposal:<id>`), and rollback restores
the exact prior blocks. The proposal records the scene's current version and never applies itself.
`review_screenplay_proposal` approves or rolls back the same records through the REST logic.

`propose_timeline_reorder` stores a reversible scene order with cumulative timings after checking
the current order; `review_timeline_proposal` applies or rolls it back. `propose_dialogue_translation`
stores a translation proposal without changing the source dialogue.

### Story operations

`apply_story_operation` shares the artifact story-operation service with
`POST /api/v1/projects/{project_id}/artifacts/{artifact_id}/operations`: `set_logline`, `add_beat`,
`add_character_arc` and `add_canon_rule`. Operations are versioned, mark dependent artifacts stale
and refresh retrieval. Over MCP they need the `story.operation` grant and approval. For the typed
storyline, characters and outline, prefer the story-entity tools and `propose_story_change`.

### Revisions, exports and backups

- `read_dialogue_translations` returns a dialogue block's linked variants;
  `read_scene_revisions` returns immutable scene snapshots.
- `render_screenplay_export` renders bounded Fountain, FDX, HTML or PDF (PDF as base64).
  `create_screenplay_export` stores an approved, checksummed export in the backup volume.
- `list_project_backups`, `create_project_backup` and `restore_project_backup` manage backups.
  Creating and restoring need approval, and a restore always creates a new project.
- `read_monty_executions` returns only redacted [Monty](monty.md) audit fields; generated code and
  inputs are never returned.
- `read_project_evaluations` returns project evaluations.

### Runs

`read_workflow_run` reads a durable run. `control_workflow_run` resumes or cancels one (grant
`runs.control` plus approval); resume restarts the same run. Over REST, runs live at
`/api/v1/projects/{project_id}/runs/{run_id}` with `POST /resume` and `POST /cancel`. Each run is a
Temporal workflow, so it survives worker restarts and browser disconnects. Runs report
`attempt_count` and `max_attempts` (1–10, default 3); a final failure stays on the run and can be
resumed.

### Permission modes

Agent runs carry a permission mode. The studio chat offers `chat_only`, `suggest` and
`project_edit` (see [Chat with the room](chat.md)). The server also supports `scoped_edit`, whose
run envelope names a target kind, target id and optional scene; proposals outside that target are
refused. `chat_only` runs can't create proposals, and approval endpoints re-check the originating
run, so a client can't bypass its stored mode.

### Legacy Copilot API

The studio chat uses AG-UI at `POST /api/v1/projects/{id}/room/chat`. The older Copilot REST
endpoints (`/api/v1/projects/{project_id}/copilot/messages`, `…/respond` and `…/respond-async`)
remain for API clients but aren't used by the studio. `respond` returns `503`, keeping the user
turn, when `LLM__ENABLED` is false or no provider is available.

## Outbound MCP client

`DraftPilotMCPClient` lets built-in agents and workflows call other MCP servers over authenticated
Streamable HTTP (tools, prompts and resources) or explicitly configured local stdio. HTTP endpoints
refuse embedded credentials, cloud metadata targets, private, link-local, reserved and multicast
addresses (including after DNS resolution); loopback stays available for local services. Responses
are size-bounded, and results must become typed DraftPilot operations before anything changes.

## Smoke check

With the stack running and an `outline.read` grant for the default local client:

```bash
uv run python scripts/mcp_smoke.py
# tools=70 resources=3 artifact_type=dict tool_type=dict
```

Set `DRAFTPILOT_MCP_ENDPOINT`, `DRAFTPILOT_MCP_TOKEN` and `DRAFTPILOT_MCP_RESOURCE` to target another
Streamable HTTP server. For a full journey, `uv run python scripts/mcp_journey.py` has an external
agent build a screenplay with writer approvals (see [Evals](evals.md#on-the-running-stack)).

## Writers' room workflows

`list_room_workflows` returns every room workflow with its parameter JSON schema, and
`start_room_workflow(project_id, workflow, params)` starts one as a durable run (capability
`room.workflow`; follow it with `read_workflow_run`). Generative workflows end in proposals the writer
reviews; analytic ones end in a report on the run. See [Writers' room](writers-room.md).
