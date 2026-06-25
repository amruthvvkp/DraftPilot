"""CRUD operations for Project."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import Project, ProjectCreate, ProjectUpdate


async def create(session: AsyncSession, data: ProjectCreate) -> Project:
    """Create and persist a new project."""
    project = Project.model_validate(data)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def get(session: AsyncSession, project_id: int) -> Project | None:
    """Return the project with the given id, or ``None`` if absent."""
    return await session.get(Project, project_id)


async def list_all(session: AsyncSession) -> list[Project]:
    """Return all projects ordered by title."""
    result = await session.exec(select(Project).order_by(col(Project.title)))
    return list(result.all())


async def update(
    session: AsyncSession, project: Project, data: ProjectUpdate
) -> Project:
    """Apply the given changes to a project and persist them."""
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def delete(session: AsyncSession, project: Project) -> None:
    """Delete the given project."""
    await session.delete(project)
    await session.commit()
