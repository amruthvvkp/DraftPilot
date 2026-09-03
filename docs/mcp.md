# MCP integration

DraftPilot exposes a typed MCP boundary from the `mcp` Compose service. The discoverable
`draftpilot://capabilities` resource lists the current capability names, scopes, and whether a
mutation requires writer approval. The `workflow_turn` prompt carries page, artifact, and selection
scope without exposing credentials. `propose_timeline_reorder` is read-safe and returns a reversible
proposal; it does not modify screenplay data.

The `retrieve_project_context` tool uses the server-side RAG service and returns project-scoped
results with source identifiers and content versions. Clients can inspect the response contract at
`draftpilot://schemas/context`; clients never receive vector-store credentials or direct database
access. Retrieval requires the `context.read` grant for the requested project and is bounded by the
MCP request timeout and output limit.

External clients should receive a project/client grant before invoking capabilities. The server must
validate both scopes and approval state; a UI permission is never authoritative. Credentials belong
in the server environment or encrypted storage and must not be sent to an MCP client. Streamable HTTP
is available on `http://localhost:9001` in local Compose; configure the client for the server's MCP
endpoint rather than the root health URL.

The Streamable HTTP transport requires `Authorization: Bearer <MCP__AUTH_TOKEN>`. Compose uses
`draftpilot-local-token` for local development; replace it before exposing port 9001 outside the
local machine. Local stdio transport is intended for a process launched by the same user and does
not need an HTTP bearer header.

Mutation tools will be added only through the same capability service, with audit records, redaction,
timeouts, output limits, and explicit consent.

The durable run API currently supports `GET` inspection, `POST /resume`, and `POST /cancel` under
`/api/v1/projects/{project_id}/runs/{run_id}`. Cancellation is history-preserving and the worker
checks the persisted state before recording success.

Copilot turns are persisted at `/api/v1/projects/{project_id}/copilot/messages`. Each message
records its page, artifact, selection, instruction layers, retrieved citations, and active typed
tools so a reconnecting client can restore context without direct database access.
