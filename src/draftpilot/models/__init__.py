"""SQLModel domain models.

Importing this package registers every table on ``SQLModel.metadata`` — Alembic
and ``create_db_and_tables`` rely on that side effect.
"""

from draftpilot.models.project import (
    Project,
    ProjectBase,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)
from draftpilot.models.scene import (
    Scene,
    SceneBase,
    SceneCreate,
    SceneRead,
    SceneUpdate,
)
from draftpilot.models.screenplay import (
    Screenplay,
    ScreenplayBase,
    ScreenplayCreate,
    ScreenplayRead,
    ScreenplayUpdate,
)

__all__ = [
    "Project",
    "ProjectBase",
    "ProjectCreate",
    "ProjectRead",
    "ProjectUpdate",
    "Screenplay",
    "ScreenplayBase",
    "ScreenplayCreate",
    "ScreenplayRead",
    "ScreenplayUpdate",
    "Scene",
    "SceneBase",
    "SceneCreate",
    "SceneRead",
    "SceneUpdate",
]
