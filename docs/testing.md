# Testing

Run the same gates CI runs before you push:

```bash
uv run pytest -q tests --ignore=tests/e2e        # Tier 0
uv run pytest tests/test_temporal_replay.py      # after any workflow edit
uv run ruff check src tests packages
uv run mypy src packages/draftpilot-mcp/src
uv run interrogate src && uv run interrogate packages/draftpilot-mcp/src
npm --prefix frontend run typecheck
npm --prefix frontend run test:run               # Vitest
npm --prefix frontend run build
```

## Test tiers

| Tier | Needs | Command | What it proves |
|---|---|---|---|
| 0 · deterministic | nothing | `uv run pytest tests --ignore=tests/e2e` | Unit and API behaviour. Runs in CI. `lmstudio` tests are deselected by default |
| e2e · browser | the running stack on `:9000` | `uv run pytest tests/e2e` | Playwright journeys. Tests are auto-marked `e2e` |
| stack · real backend | the running stack on `:9000` | `uv run pytest tests/e2e -m stack` | Browser journeys with no mocks: Big Fish import, edit, reload, Story twin, room, PDF export, duplicate and delete (`test_real_stack.py`), and the manual Storyline → Characters → Outline → Script journey (`test_manual_journey.py`). They create and clean up their own projects |
| 1 · local model | LM Studio server | `uv run pytest -m lmstudio` | Real PydanticAI calls against local LM Studio |
| postgres | the stack's Postgres (pgvector) on `:55432` | `uv run pytest -m postgres` | The pgvector hybrid retrieval store, in a throwaway schema |
| replay | nothing | `uv run pytest tests/test_temporal_replay.py` | Workflow edits still replay the recorded histories in `tests/temporal_histories/` (see [Extending the room](dev/extending-the-room.md)) |
| frontend | Node | `npm --prefix frontend run test:run` | Vitest component, reducer and API-layer tests |
| 2 · evals | LM Studio server | `uv run python -m draftpilot.evals` | Quality of the room on Big Fish against committed baselines (see [Evals and usefulness](evals.md)) |

All LLM-backed tests run against local LM Studio. They never fall back to a cloud provider. Configure
the target with the `EVAL__` settings:

- `EVAL__BASE_URL` defaults to `http://localhost:1234/v1`.
- `EVAL__CHAT_MODEL`, `EVAL__JUDGE_MODEL` and `EVAL__EMBEDDING_MODEL` pick the models. When they're
  empty, the first *loaded* model reported by `/api/v0/models` is used.

If LM Studio isn't reachable, the `lmstudio` fixture fails with a clear message instead of skipping.
Install the browser once with `uv run playwright install chromium`, and again after any Playwright
upgrade.

The isolated Python suite includes `tests/test_migrations.py`, which verifies that the Alembic
history has one current head without connecting to the developer database. Compose startup also
runs `alembic upgrade head` against its dedicated Postgres service.

Apart from the `stack` journeys, browser tests mock every project and workspace API response and
never use the Compose database as test state. The repository default is `http://localhost:9000`; use the portable Linux browser image and
Compose network for CI-style execution:

```bash
docker compose --profile test run --rm e2e
```

When the stack is not already running, start it first with `docker compose up -d --build`; the
test service waits for the UI health check. For a
repeatable CI run, use `docker compose build e2e ui` followed by the command above.

Rebuild the test image after changing Python Playwright tests or dependencies so Docker does not
reuse a cached test source layer:

```bash
docker compose --profile test build e2e
docker compose --profile test run --rm e2e
```

The `e2e` service uses the pinned Playwright Python image and targets `http://ui:8000`, making the
suite suitable for CI runners that do not have a developer browser session. It includes a single
end-to-end smoke journey as well as focused journeys.

GitHub Actions runs the same isolated command in `.github/workflows/ci.yml`. It uses Compose's
ephemeral Postgres/Redis services only for application startup; browser API calls remain mocked and
the test job removes its containers and volumes after each run.

Chat in browser tests runs on the AG-UI endpoint (`POST /api/v1/projects/{id}/room/chat`); mock its
event stream rather than calling a live model provider. Backend chat tests use a scripted
`FunctionModel`.

The local retrieval service is also portable: `docker compose up --build rag` exposes its health
endpoint at `http://localhost:9010/health`. It uses the same bearer token convention as MCP and
keeps search partitions project-scoped and persists its replaceable local embedding/lexical store in the `rag_data`
volume. The lexical implementation is intentionally replaceable with a vector-store adapter.

Screenplay exports are non-mutating: use `/api/v1/projects/{project_id}/screenplays/{screenplay_id}/exports/fountain`,
`.../fdx`, `.../html`, or `.../pdf`. PDF import is best-effort text recovery via `pypdf` (scene headings and
basic character/dialogue/action cues are inferred); encrypted, malformed, oversized, and unreadable
inputs are rejected. PDF export uses ReportLab's installed fonts; deployments that
need Indian-language or other non-Latin glyphs should add and register a suitable Unicode font.

The benchmark comparison tool is database-free. Build isolated manifests in Python with
`manifest_from_document`, or validate existing JSON fixtures directly:

```bash
uv run python scripts/benchmark_compare.py control.json candidate.json
```

The report includes scene-order, element-count, runtime, and language deltas; source screenplay
bytes are represented only by SHA-256 digests.
For a persisted isolated project, `GET /api/v1/projects/{project_id}/screenplays/{screenplay_id}/benchmark-manifest`
builds the same contract from canonical screenplay data and project language metadata. Pass
`track=redevelopment` (default) or `track=import_compare` to identify the two benchmark tracks;
invalid track values are rejected by the API.
