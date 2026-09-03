"""Versioned HTTP API routers for DraftPilot."""

from fastapi import APIRouter

from draftpilot.api.projects import router as projects_router
from draftpilot.api.runs import router as runs_router

router = APIRouter(prefix="/api/v1")
router.include_router(projects_router)
router.include_router(runs_router)

__all__ = ["router"]
