"""SQLModel domain models.

Importing this package registers every table on ``SQLModel.metadata`` — Alembic
relies on that side effect.
"""

from draftpilot.models.act import (
    Act,
    ActBase,
    ActCreate,
    ActRead,
    ActUpdate,
)
from draftpilot.models.agent_proposal import (
    AgentProposal,
    AgentProposalBase,
    AgentProposalRead,
)
from draftpilot.models.block import (
    Block,
    BlockBase,
    BlockCreate,
    BlockRead,
    BlockUpdate,
)
from draftpilot.models.copilot_message import (
    CopilotMessage,
    CopilotMessageBase,
    CopilotMessageCreate,
    CopilotMessageRead,
)
from draftpilot.models.dialogue_translation import (
    DialogueTranslation,
    DialogueTranslationBase,
    DialogueTranslationCreate,
    DialogueTranslationRead,
)
from draftpilot.models.enums import BlockType, ReferenceKind, ScreeningType
from draftpilot.models.evaluation import (
    EvaluationResult,
    EvaluationResultCreate,
    EvaluationResultRead,
)
from draftpilot.models.knowledge_graph import (
    KnowledgeEdge,
    KnowledgeEdgeBase,
    KnowledgeEdgeCreate,
    KnowledgeEdgeRead,
    KnowledgeNode,
    KnowledgeNodeBase,
    KnowledgeNodeCreate,
    KnowledgeNodeRead,
)
from draftpilot.models.mcp_access import (
    MCPApprovalRequest,
    MCPApprovalRequestRead,
    MCPAuditEvent,
    MCPClient,
    MCPClientBase,
    MCPGrant,
    MCPGrantBase,
    MCPGrantCreate,
    MCPGrantRead,
)
from draftpilot.models.monty_execution import (
    MontyExecution,
    MontyExecutionBase,
    MontyExecutionCreate,
    MontyExecutionRead,
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
from draftpilot.models.provider_profile import (
    ProviderProfile,
    ProviderProfileBase,
    ProviderProfileCreate,
    ProviderProfileRead,
    ProviderProfileUpdate,
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
from draftpilot.models.story_artifact import (
    StoryArtifact,
    StoryArtifactBase,
    StoryArtifactRead,
)
from draftpilot.models.timeline_proposal import (
    TimelineProposalBase,
    TimelineProposalRead,
    TimelineProposalRecord,
)
from draftpilot.models.workflow_run import (
    WorkflowRun,
    WorkflowRunBase,
    WorkflowRunCreate,
    WorkflowRunRead,
)

__all__ = [
    "Act",
    "ActBase",
    "ActCreate",
    "ActRead",
    "ActUpdate",
    "AgentProposal",
    "AgentProposalBase",
    "AgentProposalRead",
    "Block",
    "BlockBase",
    "BlockCreate",
    "BlockRead",
    "BlockType",
    "BlockUpdate",
    "CopilotMessage",
    "CopilotMessageBase",
    "CopilotMessageCreate",
    "CopilotMessageRead",
    "DialogueTranslation",
    "DialogueTranslationBase",
    "DialogueTranslationCreate",
    "DialogueTranslationRead",
    "EvaluationResult",
    "EvaluationResultCreate",
    "EvaluationResultRead",
    "KnowledgeEdge",
    "KnowledgeEdgeBase",
    "KnowledgeEdgeCreate",
    "KnowledgeEdgeRead",
    "KnowledgeNode",
    "KnowledgeNodeBase",
    "KnowledgeNodeCreate",
    "KnowledgeNodeRead",
    "MCPApprovalRequest",
    "MCPApprovalRequestRead",
    "MCPAuditEvent",
    "MCPClient",
    "MCPClientBase",
    "MCPGrant",
    "MCPGrantBase",
    "MCPGrantCreate",
    "MCPGrantRead",
    "MontyExecution",
    "MontyExecutionBase",
    "MontyExecutionCreate",
    "MontyExecutionRead",
    "Project",
    "ProjectBase",
    "ProjectCreate",
    "ProjectRead",
    "ProjectReference",
    "ProjectReferenceBase",
    "ProjectReferenceCreate",
    "ProjectReferenceRead",
    "ProjectReferenceUpdate",
    "ProjectUpdate",
    "ProviderProfile",
    "ProviderProfileBase",
    "ProviderProfileCreate",
    "ProviderProfileRead",
    "ProviderProfileUpdate",
    "ReferenceKind",
    "Scene",
    "SceneBase",
    "SceneCreate",
    "SceneRead",
    "SceneRevision",
    "SceneRevisionBase",
    "SceneRevisionRead",
    "SceneUpdate",
    "ScreeningType",
    "Screenplay",
    "ScreenplayBase",
    "ScreenplayCreate",
    "ScreenplayRead",
    "ScreenplayUpdate",
    "StoryArtifact",
    "StoryArtifactBase",
    "StoryArtifactRead",
    "TimelineProposalBase",
    "TimelineProposalRead",
    "TimelineProposalRecord",
    "WorkflowRun",
    "WorkflowRunBase",
    "WorkflowRunCreate",
    "WorkflowRunRead",
    "validate_language_separation",
]
