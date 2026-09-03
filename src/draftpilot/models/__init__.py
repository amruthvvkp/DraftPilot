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
from draftpilot.models.dialogue_translation import (
    DialogueTranslation,
    DialogueTranslationBase,
    DialogueTranslationCreate,
    DialogueTranslationRead,
)
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
from draftpilot.models.workflow_run import (
    WorkflowRun,
    WorkflowRunBase,
    WorkflowRunCreate,
    WorkflowRunRead,
)
from draftpilot.models.timeline_proposal import (
    TimelineProposalBase,
    TimelineProposalRead,
    TimelineProposalRecord,
)
from draftpilot.models.story_artifact import StoryArtifact, StoryArtifactBase, StoryArtifactRead
from draftpilot.models.agent_proposal import AgentProposal, AgentProposalBase, AgentProposalRead
from draftpilot.models.mcp_access import MCPAuditEvent, MCPClient, MCPClientBase, MCPGrant, MCPGrantBase, MCPGrantCreate, MCPGrantRead

__all__ = [
    "BlockType",
    "ReferenceKind",
    "ScreeningType",
    "DialogueTranslation",
    "DialogueTranslationBase",
    "DialogueTranslationCreate",
    "DialogueTranslationRead",
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
    "WorkflowRun",
    "WorkflowRunBase",
    "WorkflowRunCreate",
    "WorkflowRunRead",
    "TimelineProposalBase",
    "TimelineProposalRead",
    "TimelineProposalRecord",
    "StoryArtifact",
    "StoryArtifactBase",
    "StoryArtifactRead",
    "AgentProposal",
    "AgentProposalBase",
    "AgentProposalRead",
    "MCPAuditEvent",
    "MCPClient",
    "MCPClientBase",
    "MCPGrant",
    "MCPGrantBase",
    "MCPGrantCreate",
    "MCPGrantRead",
]
