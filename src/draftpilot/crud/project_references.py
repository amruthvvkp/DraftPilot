"""CRUD operations for ProjectReference."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import (
    ProjectReference,
    ProjectReferenceCreate,
    ProjectReferenceUpdate,
)


async def create(session: AsyncSession, data: ProjectReferenceCreate) -> ProjectReference:
    """Create and persist a new project reference."""
    reference = ProjectReference.model_validate(data)
    session.add(reference)
    await session.commit()
    await session.refresh(reference)
    return reference


async def get(session: AsyncSession, reference_id: int) -> ProjectReference | None:
    """Return the project reference with the given id, or ``None`` if absent."""
    return await session.get(ProjectReference, reference_id)


async def list_for_project(session: AsyncSession, project_id: int) -> list[ProjectReference]:
    """Return all references for a project ordered by id."""
    result = await session.exec(
        select(ProjectReference)
        .where(ProjectReference.project_id == project_id)
        .order_by(col(ProjectReference.id))
    )
    return list(result.all())


async def update(
    session: AsyncSession, reference: ProjectReference, data: ProjectReferenceUpdate
) -> ProjectReference:
    """Apply the given changes to a project reference and persist them."""
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(reference, key, value)
    session.add(reference)
    await session.commit()
    await session.refresh(reference)
    return reference


async def delete(session: AsyncSession, reference: ProjectReference) -> None:
    """Delete the given project reference."""
    await session.delete(reference)
    await session.commit()
