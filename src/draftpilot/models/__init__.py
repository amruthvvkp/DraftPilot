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
from draftpilot.models.evaluation import (
    EvaluationResult,
    EvaluationResultCreate,
    EvaluationResultRead,
)
from draftpilot.models.project import (
    Project,
    ProjectBase,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    validate_language_separation,
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
from draftpilot.models.provider_profile import ProviderProfile, ProviderProfileBase, ProviderProfileCreate, ProviderProfileRead, ProviderProfileUpdate
from draftpilot.models.copilot_message import CopilotMessage, CopilotMessageBase, CopilotMessageCreate, CopilotMessageRead
from draftpilot.models.knowledge_graph import KnowledgeEdge, KnowledgeEdgeBase, KnowledgeEdgeCreate, KnowledgeEdgeRead, KnowledgeNode, KnowledgeNodeBase, KnowledgeNodeCreate, KnowledgeNodeRead

__all__ = [
    "BlockType",
    "ReferenceKind",
    "ScreeningType",
    "DialogueTranslation",
    "DialogueTranslationBase",
    "DialogueTranslationCreate",
    "DialogueTranslationRead",
    "EvaluationResult",
    "EvaluationResultCreate",
    "EvaluationResultRead",
    "Project",
    "ProjectBase",
    "ProjectCreate",
    "ProjectRead",
    "ProjectUpdate",
    "validate_language_separation",
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
    "ProviderProfile",
    "ProviderProfileBase",
    "ProviderProfileCreate",
    "ProviderProfileRead",
    "ProviderProfileUpdate",
    "CopilotMessage",
    "CopilotMessageBase",
    "CopilotMessageCreate",
    "CopilotMessageRead",
    "KnowledgeNode",
    "KnowledgeNodeBase",
    "KnowledgeNodeCreate",
    "KnowledgeNodeRead",
    "KnowledgeEdge",
    "KnowledgeEdgeBase",
    "KnowledgeEdgeCreate",
    "KnowledgeEdgeRead",
]
