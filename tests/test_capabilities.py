"""Test the shared MCP capability catalog contract."""

from draftpilot.core.capabilities import capability_catalog


def test_catalog_contains_scoped_read_and_approved_mutation_capabilities() -> None:
    """Expose read capabilities while marking mutations for approval."""
    catalog = {capability.name: capability for capability in capability_catalog()}
    assert catalog["screenplay.read"].scope == "scene"
    assert catalog["timeline.propose"].mutates is False
    assert catalog["revisions.restore"].mutates is True
    assert catalog["revisions.restore"].approval_required is True
