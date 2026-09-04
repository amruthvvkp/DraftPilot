"""Versioned HTTP API routers for DraftPilot."""

from fastapi import APIRouter

from draftpilot.api.projects import router as projects_router
from draftpilot.api.runs import router as runs_router
from draftpilot.api.timeline import router as timeline_router
from draftpilot.api.artifacts import router as artifacts_router
from draftpilot.api.exports import router as exports_router
from draftpilot.api.evaluations import router as evaluations_router
from draftpilot.api.agent import router as agent_router
from draftpilot.api.mcp_access import router as mcp_access_router
from draftpilot.api.backups import router as backups_router
from draftpilot.api.providers import router as providers_router
from draftpilot.api.copilot import router as copilot_router
from draftpilot.api.knowledge_graph import router as knowledge_graph_router
from draftpilot.api.agent_roles import router as agent_roles_router
from draftpilot.api.capabilities import router as capabilities_router

router = APIRouter(prefix="/api/v1")
router.include_router(projects_router)
router.include_router(runs_router)
router.include_router(timeline_router)
router.include_router(artifacts_router)
router.include_router(exports_router)
router.include_router(evaluations_router)
router.include_router(agent_router)
router.include_router(mcp_access_router)
router.include_router(backups_router)
router.include_router(providers_router)
router.include_router(copilot_router)
router.include_router(knowledge_graph_router)
router.include_router(agent_roles_router)
router.include_router(capabilities_router)

__all__ = ["router"]
