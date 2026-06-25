---
name: add-model
description: Scaffold a new SQLModel domain model for DraftPilot with its CRUD helpers and an Alembic migration. Use when adding a database table or entity.
---

# Add a domain model

1. **Model** — create `src/draftpilot/models/<name>.py` following the existing hierarchy:

   ```python
   class ThingBase(SQLModel):
       name: str = Field(index=True, max_length=200)

   class Thing(ThingBase, TimestampMixin, table=True):
       __tablename__ = "thing"
       id: int | None = Field(default=None, primary_key=True)

   class ThingCreate(ThingBase): ...
   class ThingUpdate(SQLModel): name: str | None = None
   class ThingRead(ThingBase): id: int
   ```

   Use `Relationship(...)` with `back_populates` for associations; reuse `TimestampMixin` from
   `models/base.py`.

2. **Register** — export the new classes from `src/draftpilot/models/__init__.py` so they land on
   `SQLModel.metadata`.

3. **CRUD** — add `src/draftpilot/crud/<name>.py` mirroring `crud/projects.py`
   (`create` / `get` / `list_*` / `update` / `delete`) and export it from `crud/__init__.py`.

4. **Migration** — with a Postgres reachable (`docker compose up -d postgres`):

   ```bash
   uv run alembic revision --autogenerate -m "add thing"
   uv run alembic upgrade head
   ```

   Review the generated file in `migrations/versions/` before committing.

5. **Verify** — `uv run python -c "import draftpilot.models; from sqlmodel import SQLModel; print(sorted(SQLModel.metadata.tables))"`,
   then `uv run interrogate src` and `uv run --group dev mypy src`.

Every class (including `*Base`/`*Create`/`*Update`/`*Read`) and function needs a one-line Sphinx
docstring and full type hints. Add `# type: ignore[call-arg]` to the `table=True` class line.
