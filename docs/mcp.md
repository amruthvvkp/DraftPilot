# MCP integration

DraftPilot exposes a typed MCP boundary from the `mcp` Compose service. The discoverable
`draftpilot://capabilities` resource lists the current capability names, scopes, and whether a
mutation requires writer approval. The `workflow_turn` prompt carries page, artifact, and selection
scope without exposing credentials. `propose_timeline_reorder` is read-safe and returns a reversible
proposal; it does not modify screenplay data.

External clients should receive a project/client grant before invoking capabilities. The server must
validate both scopes and approval state; a UI permission is never authoritative. Credentials belong
in the server environment or encrypted storage and must not be sent to an MCP client. Streamable HTTP
is available on `http://localhost:9001` in local Compose; configure the client for the server's MCP
endpoint rather than the root health URL.

Mutation tools will be added only through the same capability service, with audit records, redaction,
timeouts, output limits, and explicit consent.
