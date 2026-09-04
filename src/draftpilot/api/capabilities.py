"""Discover server-authoritative Copilot capability bundles."""

from fastapi import APIRouter, Query

from draftpilot.core.capabilities import Capability, capabilities_for_page, capability_catalog

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("", response_model=list[Capability])
def list_capabilities(
    page: str | None = Query(default=None, min_length=1, max_length=200),
) -> list[Capability]:
    """Return the capability catalog or the scoped bundle for one workflow page."""
    if page is None:
        return capability_catalog()
    names = set(capabilities_for_page(page))
    return [capability for capability in capability_catalog() if capability.name in names]
