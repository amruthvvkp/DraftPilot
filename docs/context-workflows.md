# Context-generation workflows

DraftPilot exposes reusable, provider-backed context workflows under
`/api/v1/projects/{project_id}/context/workflows`. The catalog declares each workflow's accepted
artifact kinds, output kind, evaluator, agent role, and default permission mode. Current workflows
cover reference scenes, visual language, camera, lighting, color palettes, film/director/style
research, and continuity.

Start a run with `POST .../runs` and provide a compatible `artifact_id` plus a writer instruction.
The API persists a `context_generation` workflow run and enqueues it for the ARQ worker. The worker
retrieves project-scoped citations through the RAG service and invokes the configured PydanticAI
provider. A successful result contains the suggestion, citations, source artifact version, output
kind, and evaluator contract. It is explicitly review-only: it never mutates canonical artifacts
or graph nodes. Poll `GET /api/v1/projects/{project_id}/runs/{run_id}` after a disconnect and review
the suggestion before creating or approving a typed change.

The React project-context page provides the same contract through the Context workflows panel. It
filters source artifacts using the server catalog and shows run status and citations. No API key or
provider credential is sent to the browser.
