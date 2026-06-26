"""SQLModel domain models.

Importing this package registers every table on ``SQLModel.metadata`` — Alembic
and ``create_db_and_tables`` rely on that side effect.
"""

from draftpilot.models.act import (
    Act,
    ActBase,
    ActCreate,
    ActRead,
    ActUpdate,
)
from draftpilot.models.block import (
    Block,
    BlockBase,
    BlockCreate,
    BlockRead,
    BlockUpdate,
)
from draftpilot.models.enums import BlockType, ReferenceKind, ScreeningType
from draftpilot.models.project import (
    Project,
    ProjectBase,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)
from draftpilot.models.project_reference import (
    ProjectReference,
    ProjectReferenceBase,
    ProjectReferenceCreate,
    ProjectReferenceRead,
    ProjectReferenceUpdate,
)
from draftpilot.models.scene import (
    Scene,
    SceneBase,
    SceneCreate,
    SceneRead,
    SceneUpdate,
)
from draftpilot.models.scene_revision import (
    SceneRevision,
    SceneRevisionBase,
    SceneRevisionRead,
)
from draftpilot.models.screenplay import (
    Screenplay,
    ScreenplayBase,
    ScreenplayCreate,
    ScreenplayRead,
    ScreenplayUpdate,
)

__all__ = [
    "BlockType",
    "ReferenceKind",
    "ScreeningType",
    "Project",
    "ProjectBase",
    "ProjectCreate",
    "ProjectRead",
    "ProjectUpdate",
    "ProjectReference",
    "ProjectReferenceBase",
    "ProjectReferenceCreate",
    "ProjectReferenceRead",
    "ProjectReferenceUpdate",
    "Screenplay",
    "ScreenplayBase",
    "ScreenplayCreate",
    "ScreenplayRead",
    "ScreenplayUpdate",
    "Act",
    "ActBase",
    "ActCreate",
    "ActRead",
    "ActUpdate",
    "Scene",
    "SceneBase",
    "SceneCreate",
    "SceneRead",
    "SceneUpdate",
    "Block",
    "BlockBase",
    "BlockCreate",
    "BlockRead",
    "BlockUpdate",
    "SceneRevision",
    "SceneRevisionBase",
    "SceneRevisionRead",
]
