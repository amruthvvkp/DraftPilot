---
name: sqlmodel-data
description: Work on the DraftPilot data layer — SQLModel models, async sessions, CRUD helpers, and Alembic migrations. Use when evolving the schema or DB connectivity (to scaffold one model end-to-end, see add-model).
---

# SQLModel data layer (DraftPilot)

Postgres via SQLModel + asyncpg (async app engine) with Alembic for migrations. Read
`src/draftpilot/core/CLAUDE.md` first.

## Layout

- `core/db/database.py` — async engine + `async_session_factory` (uses SQLModel's
  `AsyncSession`, which has `.exec()`), `session_scope()`, `async_get_db()`,
  `create_db_and_tables()` (dev bootstrap only — Alembic owns production).
- `models/` — `*Base` → table model (`table=True`) → `*Read`/`*Create`/`*Update` per entity.
  `models/base.py` has `TimestampMixin`. `models/__init__.py` imports all so every table
  lands on `SQLModel.metadata`.
- `crud/` — thin async helpers per model (`create`/`get`/`list_*`/`update`/`delete`).
- `migrations/` — Alembic; `env.py` reads `settings.postgres.sync_dsn` (psycopg) and targets
  `SQLModel.metadata`.

## Conventions / gotchas

- **Sessions**: use SQLModel's `AsyncSession` (`from sqlmodel.ext.asyncio.session import
  AsyncSession`) so `.exec()` is available; `async_session_factory` is built with
  `class_=AsyncSession`.
- **Typed columns in queries**: wrap with `col()` for ordering/filtering on typed fields,
  e.g. `select(Scene).order_by(col(Scene.position))` — avoids mypy `int` vs Column errors.
- **Timestamps**: timezone-aware. `TimestampMixin` uses `sa_type=DateTime(timezone=True)`
  (NOT a shared `sa_column` — that can't bind to multiple tables). asyncpg rejects
  aware datetimes into naive columns, so keep columns `timestamp with time zone`.
- **DSNs**: `settings.postgres.async_dsn` (app, asyncpg) vs `sync_dsn` (Alembic, psycopg).

## Migration workflow

After changing models:

```bash
docker compose up -d postgres            # or any reachable Postgres
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

Review the generated file in `migrations/versions/` before committing. To regenerate from
scratch against a throwaway DB, start a temporary `postgres:16-alpine`, point the
`POSTGRES__*` env at it (inline the vars — zsh does not word-split `$VAR`), autogenerate,
then remove the container.

## Code style

Every module, class (including the `*Base`/`*Create`/`*Update`/`*Read` schema classes), function,
and method needs a one-line Sphinx docstring, and every signature needs full type hints. New
`table=True` models carry `# type: ignore[call-arg]`. Interrogate enforces 100%; mypy must stay clean.

## Verify

```bash
uv run python -c "import draftpilot.models; from sqlmodel import SQLModel; print(sorted(SQLModel.metadata.tables))"
uv run ruff check src && uv run --group dev mypy src
```
