"""Delete and duplicate whole projects safely: a backup always comes first, and nothing is left dangling."""

from typing import Any

from sqlalchemy import ColumnElement, Table, delete, select
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.backup import BackupError, read_backup, write_backup
from draftpilot.core.config import settings
from draftpilot.crud import projects as projects_crud
from draftpilot.models import Project


def _scope(table: Table, project_id: int, seen: frozenset[str] = frozenset()) -> ColumnElement[bool] | None:
    """Return the condition selecting a table's rows that belong to one project, or ``None`` if it has none.

    A row belongs to a project when it has that ``project_id``, or points (by foreign key) at a row that does.
    """
    if "project_id" in table.c and table.name != "project":
        return table.c.project_id == project_id
    for column in table.c:
        for foreign_key in column.foreign_keys:
            parent = foreign_key.column.table
            if parent.name == "project" or parent.name in seen or parent is table:
                continue
            parent_scope = _scope(parent, project_id, seen | {table.name})  # type: ignore[arg-type]
            if parent_scope is not None:
                return column.in_(select(foreign_key.column).where(parent_scope))
    return None


def project_tables() -> list[Table]:
    """Return every table holding project data, children before parents (safe deletion order)."""
    return [
        table
        for table in reversed(SQLModel.metadata.sorted_tables)
        if table.name != "project" and _scope(table, 0) is not None
    ]


async def purge_project(session: AsyncSession, project_id: int) -> dict[str, int]:
    """Delete a project and everything that belongs to it; return the rows removed per table."""
    removed: dict[str, int] = {}
    for table in project_tables():
        condition = _scope(table, project_id)
        assert condition is not None
        result = await session.exec(delete(table).where(condition))  # type: ignore[call-overload]
        if result.rowcount:
            removed[table.name] = result.rowcount
    await session.exec(delete(Project).where(Project.id == project_id))  # type: ignore[call-overload,arg-type]
    await session.commit()
    return removed


async def delete_project(session: AsyncSession, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Back the project up, then purge it; return the backup filename so it can be restored."""
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise LookupError("Project not found")
    filename, _manifest = write_backup(settings.backup.root, project_id, payload, settings.metadata.version, f"{project.title} (deleted)")
    removed = await purge_project(session, project_id)
    return {"project_id": project_id, "title": project.title, "backup": filename, "removed": removed}


async def deleted_project_backups(session: AsyncSession) -> list[dict[str, Any]]:
    """Return the newest backup of every project that no longer exists (so it can be restored)."""
    if not settings.backup.root.exists():
        return []
    existing = {project.id for project in await projects_crud.list_all(session)}
    newest: dict[int, dict[str, Any]] = {}
    for path in sorted(settings.backup.root.glob("*.json.gz")):
        try:
            envelope = read_backup(settings.backup.root, path.name)
        except BackupError:
            continue
        manifest = envelope.manifest
        if manifest.project_id in existing or path.with_name(f"{path.name}.restored").exists():
            continue
        current = newest.get(manifest.project_id)
        if current is None or manifest.created_at > current["manifest"].created_at:
            title = envelope.payload.get("project", {}).get("title", f"Project {manifest.project_id}")
            newest[manifest.project_id] = {"filename": path.name, "manifest": manifest, "title": title}
    return sorted(newest.values(), key=lambda item: item["manifest"].created_at, reverse=True)
