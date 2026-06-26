"""Thin async CRUD helpers built directly on the SQLModel session."""

from draftpilot.crud import (
    acts,
    blocks,
    project_references,
    projects,
    scene_revisions,
    scenes,
    screenplays,
)

__all__ = [
    "projects",
    "screenplays",
    "acts",
    "scenes",
    "blocks",
    "project_references",
    "scene_revisions",
]
