"""Test server-authoritative capability authorization."""

from datetime import UTC, datetime, timedelta

import pytest

from draftpilot.core.authorization import (
    CapabilityGrant,
    CapabilityRequest,
    authorize,
    redact_audit_payload,
)


def test_mutation_requires_matching_scope_and_explicit_approval() -> None:
    """Require a valid client/project grant and writer approval for mutation."""
    grant = CapabilityGrant(client_id="claude", project_id=4, capability="revisions.restore")
    request = CapabilityRequest(client_id="claude", project_id=4, capability="revisions.restore")
    with pytest.raises(PermissionError, match="approval"):
        authorize(request, [grant])
    authorize(request.model_copy(update={"approved": True}), [grant])


def test_authorization_rejects_expired_or_cross_project_grants() -> None:
    """Reject grants that cannot authorize the requested project now."""
    grant = CapabilityGrant(
        client_id="claude",
        project_id=4,
        capability="screenplay.read",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    request = CapabilityRequest(client_id="claude", project_id=5, capability="screenplay.read")
    with pytest.raises(PermissionError, match="not granted"):
        authorize(request, [grant])


def test_audit_redaction_is_case_insensitive() -> None:
    """Remove credentials from audit payloads while retaining useful metadata."""
    assert redact_audit_payload({"Api_Key": "secret", "project_id": 4}, {"api_key"}) == {
        "Api_Key": "[REDACTED]",
        "project_id": 4,
    }
