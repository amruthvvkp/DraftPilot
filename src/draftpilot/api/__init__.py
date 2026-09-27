"""Versioned HTTP API routers for DraftPilot."""

from fastapi import APIRouter, Depends, Request

from draftpilot.api.agent import router as agent_router
from draftpilot.api.agent_roles import router as agent_roles_router
from draftpilot.api.artifacts import router as artifacts_router
from draftpilot.api.auth import require_api_auth
from draftpilot.api.auth import router as auth_router
from draftpilot.api.backups import router as backups_router
from draftpilot.api.capabilities import router as capabilities_router
from draftpilot.api.context_workflows import router as context_workflows_router
from draftpilot.api.copilot import router as copilot_router
from draftpilot.api.evaluations import router as evaluations_router
from draftpilot.api.events import router as events_router
from draftpilot.api.exports import router as exports_router
from draftpilot.api.insights import router as insights_router
from draftpilot.api.knowledge_graph import router as knowledge_graph_router
from draftpilot.api.lifecycle import router as lifecycle_router
from draftpilot.api.mcp_access import router as mcp_access_router
from draftpilot.api.mcp_approvals import router as mcp_approvals_router
from draftpilot.api.monty import router as monty_router
from draftpilot.api.projects import router as projects_router
from draftpilot.api.providers import router as providers_router
from draftpilot.api.retrieval import router as retrieval_router
from draftpilot.api.room import router as room_router
from draftpilot.api.runs import router as runs_router
from draftpilot.api.timeline import router as timeline_router
from draftpilot.api.twins import project_router as twin_router
from draftpilot.api.twins import writer_router
from draftpilot.core import events

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)



async def bind_request_client(request: Request) -> None:
    """Tag this request's change events with the originating browser tab."""
    events.bind_client(request.headers.get(events.CLIENT_HEADER))


# Everything except the auth endpoints requires the configured API token or session.
protected = APIRouter(dependencies=[Depends(require_api_auth), Depends(bind_request_client)])
protected.include_router(lifecycle_router)  # before projects_router: /projects/deleted must win over /{project_id}
protected.include_router(projects_router)
protected.include_router(runs_router)
protected.include_router(timeline_router)
protected.include_router(artifacts_router)
protected.include_router(exports_router)
protected.include_router(evaluations_router)
protected.include_router(agent_router)
protected.include_router(mcp_access_router)
protected.include_router(backups_router)
protected.include_router(providers_router)
protected.include_router(copilot_router)
protected.include_router(knowledge_graph_router)
protected.include_router(agent_roles_router)
protected.include_router(capabilities_router)
protected.include_router(context_workflows_router)
protected.include_router(monty_router)
protected.include_router(mcp_approvals_router)
protected.include_router(events_router)
protected.include_router(room_router)
protected.include_router(retrieval_router)
protected.include_router(twin_router)
protected.include_router(writer_router)
protected.include_router(insights_router)
router.include_router(protected)

__all__ = ["router"]
