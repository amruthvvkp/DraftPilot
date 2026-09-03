"""Test the built-in agent role contract."""

import pytest
from pydantic import ValidationError

from draftpilot.api.runs import RunCreateRequest
from draftpilot.core.agent_roles import AGENT_ROLES, agent_roles


def test_agent_role_catalog_contains_supported_roles() -> None:
    """Expose every supported built-in role with a safe default permission."""
    assert [role.key for role in agent_roles()] == [role.key for role in AGENT_ROLES]
    assert len(AGENT_ROLES) == 7
    assert {role.default_permission for role in AGENT_ROLES} == {"chat_only"}


def test_run_request_rejects_unknown_agent_role() -> None:
    """Reject role names outside the server-owned catalog."""
    with pytest.raises(ValidationError):
        RunCreateRequest(screenplay_id=1, agent_role="untrusted_role")
