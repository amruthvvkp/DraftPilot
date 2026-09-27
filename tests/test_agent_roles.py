"""Test the built-in agent role contract."""

import pytest
from pydantic import ValidationError

from draftpilot.agents.specs import load_specs
from draftpilot.api.runs import RunCreateRequest
from draftpilot.core.agent_roles import AGENT_ROLES, agent_roles


def test_agent_role_catalog_contains_supported_roles() -> None:
    """Expose every supported built-in role with a safe default permission."""
    assert [role.key for role in agent_roles()] == [role.key for role in AGENT_ROLES]
    assert len(AGENT_ROLES) == 13
    assert {role.default_permission for role in AGENT_ROLES} == {"chat_only"}


def test_every_catalogue_role_has_a_spec() -> None:
    """Keep the role catalogue and the agent specs in lockstep."""
    assert {role.key for role in AGENT_ROLES} == set(load_specs())


def test_run_request_rejects_unknown_agent_role() -> None:
    """Reject role names outside the server-owned catalog."""
    with pytest.raises(ValidationError):
        RunCreateRequest(screenplay_id=1, agent_role="untrusted_role")
