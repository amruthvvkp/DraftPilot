"""Test the shared MCP capability catalog contract."""

from draftpilot.core.capabilities import capabilities_for_page, capability_catalog


def test_catalog_contains_scoped_read_and_approved_mutation_capabilities() -> None:
    """Expose read capabilities while marking mutations for approval."""
    catalog = {capability.name: capability for capability in capability_catalog()}
    assert catalog["screenplay.read"].scope == "scene"
    assert catalog["timeline.propose"].mutates is False
    assert catalog["revisions.restore"].mutates is True
    assert catalog["revisions.restore"].approval_required is True


def test_page_capabilities_are_server_authoritative() -> None:
    """Route each workflow page to only its typed capability bundle."""
    assert "timeline.propose" in capabilities_for_page("/projects/7/timeline")
    assert "outline.read" not in capabilities_for_page("/projects/7/timeline")
    assert capabilities_for_page("unknown") == ["screenplay.read", "context.read", "revisions.read"]
