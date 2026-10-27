"""Thin async CRUD helpers built directly on the SQLModel session."""

from draftpilot.crud import (
    acts,
    blocks,
    project_references,
    projects,
    provider_profiles,
    scene_revisions,
    scenes,
    screenplays,
)

__all__ = [
    "acts",
    "blocks",
    "project_references",
    "projects",
    "provider_profiles",
    "scene_revisions",
    "scenes",
    "screenplays",
]
