"""Versioned HTTP API routers for DraftPilot."""

from fastapi import APIRouter

from draftpilot.api.projects import router as projects_router
from draftpilot.api.runs import router as runs_router
from draftpilot.api.timeline import router as timeline_router
from draftpilot.api.artifacts import router as artifacts_router
from draftpilot.api.exports import router as exports_router

router = APIRouter(prefix="/api/v1")
router.include_router(projects_router)
router.include_router(runs_router)
router.include_router(timeline_router)
router.include_router(artifacts_router)
router.include_router(exports_router)

__all__ = ["router"]
