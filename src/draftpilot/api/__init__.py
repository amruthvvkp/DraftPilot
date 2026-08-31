"""Versioned HTTP API routers for DraftPilot."""

from fastapi import APIRouter

from draftpilot.api.projects import router as projects_router

router = APIRouter(prefix="/api/v1")
router.include_router(projects_router)

__all__ = ["router"]
