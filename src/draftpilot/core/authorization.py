"""Server-authoritative capability grants and approval checks."""

import hashlib
import json
from datetime import UTC, datetime

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
    # Set only by the server after verifying a writer-decided approval request.
    approved: bool = False


class ApprovalRequiredError(PermissionError):
    """Signal that a writer must approve a recorded request before the call may run."""

    def __init__(self, approval_id: int) -> None:
        """Describe the pending approval request the client must wait for."""
        self.approval_id = approval_id
        super().__init__(
            f"Writer approval is required: approval request {approval_id} is pending. "
            f"Ask the writer to approve it in DraftPilot, then retry with approval_id={approval_id}."
        )


def arguments_digest(capability: str, action: str, arguments: dict[str, object]) -> str:
    """Return a stable digest binding an approval to the exact invocation arguments."""
    canonical = json.dumps(
        {"capability": capability, "action": action, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def authorize(request: CapabilityRequest, grants: list[CapabilityGrant]) -> None:
    """Authorize a scoped capability or raise a precise permission error."""
    capability = next(
        (item for item in capability_catalog() if item.name == request.capability), None
    )
    if capability is None:
        raise PermissionError("Unknown capability")
    now = datetime.now(UTC)
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
    if requires_approval(request.capability) and not request.approved:
        raise PermissionError("Writer approval is required for this capability")


def requires_approval(capability_name: str) -> bool:
    """Return whether a catalog capability needs a writer-decided approval."""
    capability = next((item for item in capability_catalog() if item.name == capability_name), None)
    return capability is not None and capability.approval_required


def redact_audit_payload(payload: dict[str, object], sensitive_keys: set[str]) -> dict[str, object]:
    """Redact sensitive audit fields before recording an invocation."""
    return {
        key: "[REDACTED]" if key.casefold() in {item.casefold() for item in sensitive_keys} else value
        for key, value in payload.items()
    }
