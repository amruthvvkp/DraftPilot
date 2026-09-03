# Testing

Run the isolated Python suite and static gates with the local UV cache:

```bash
UV_CACHE_DIR=/private/tmp/draftpilot-uv-cache uv run --group ui pytest -q tests --ignore=tests/e2e
UV_CACHE_DIR=/private/tmp/draftpilot-uv-cache uv run --group ui ruff check src tests
UV_CACHE_DIR=/private/tmp/draftpilot-uv-cache uv run --group ui mypy src
UV_CACHE_DIR=/private/tmp/draftpilot-uv-cache uv run --group ui interrogate src migrations
```

Browser tests mock every project/workspace API response and never use the Compose database as test
state. Run them locally with `--base-url http://localhost:9000`, or use the portable Linux browser
image and Compose network:

```bash
docker compose --profile test run --rm e2e
```

The `e2e` service uses the pinned Playwright Python image and targets `http://ui:8000`, making the
suite suitable for CI runners that do not have a developer browser session.
