"""Server-authoritative capability grants and approval checks."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from draftpilot.core.capabilities import capability_catalog


class CapabilityGrant(BaseModel):
    """Grant one client a named capability within one project scope."""

    client_id: str = Field(min_length=1, max_length=200)
    project_id: int
    capability: str
    expires_at: datetime | None = None


class CapabilityRequest(BaseModel):
    """Describe a capability invocation requiring server authorization."""

    client_id: str = Field(min_length=1, max_length=200)
    project_id: int
    capability: str
    approved: bool = False


def authorize(request: CapabilityRequest, grants: list[CapabilityGrant]) -> None:
    """Authorize a scoped capability or raise a precise permission error."""
    capability = next(
        (item for item in capability_catalog() if item.name == request.capability), None
    )
    if capability is None:
        raise PermissionError("Unknown capability")
    now = datetime.now(timezone.utc)
    granted = next(
        (
            grant
            for grant in grants
            if grant.client_id == request.client_id
            and grant.project_id == request.project_id
            and grant.capability == request.capability
            and (grant.expires_at is None or grant.expires_at > now)
        ),
        None,
    )
    if granted is None:
        raise PermissionError("Capability is not granted for this client and project")
    if capability.approval_required and not request.approved:
        raise PermissionError("Writer approval is required for this capability")


def redact_audit_payload(payload: dict[str, object], sensitive_keys: set[str]) -> dict[str, object]:
    """Redact sensitive audit fields before recording an invocation."""
    return {
        key: "[REDACTED]" if key.casefold() in {item.casefold() for item in sensitive_keys} else value
        for key, value in payload.items()
    }
