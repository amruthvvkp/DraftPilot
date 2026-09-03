# Testing

Run the isolated Python suite and static gates with the local UV cache:

```bash
UV_CACHE_DIR=/private/tmp/draftpilot-uv-cache uv run --group ui pytest -q tests --ignore=tests/e2e
UV_CACHE_DIR=/private/tmp/draftpilot-uv-cache uv run --group ui ruff check src tests
UV_CACHE_DIR=/private/tmp/draftpilot-uv-cache uv run --group ui mypy src
UV_CACHE_DIR=/private/tmp/draftpilot-uv-cache uv run --group ui interrogate src migrations
```

Browser tests mock every project/workspace API response and never use the Compose database as test
state. The repository default is `http://localhost:9000`; use the portable Linux browser image and
Compose network for CI-style execution:

```bash
docker compose --profile test run --rm e2e
```

The `e2e` service uses the pinned Playwright Python image and targets `http://ui:8000`, making the
suite suitable for CI runners that do not have a developer browser session.

Copilot browser turns use the persisted asynchronous run contract; tests should mock both the
`respond-async` response and the project-scoped run polling response rather than invoking a live
model provider.

The local retrieval service is also portable: `docker compose up --build rag` exposes its health
endpoint at `http://localhost:9010/health`. It uses the same bearer token convention as MCP and
keeps search partitions project-scoped and persists its initial lexical store in the `rag_data`
volume. The lexical implementation is intentionally replaceable with a vector-store adapter.

Screenplay exports are non-mutating: use `/api/v1/projects/{project_id}/screenplays/{screenplay_id}/exports/fountain`,
`.../fdx`, or `.../pdf`. PDF is best-effort and uses ReportLab's installed fonts; deployments that
need Indian-language or other non-Latin glyphs should add and register a suitable Unicode font.
