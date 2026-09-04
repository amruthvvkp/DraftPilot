"""Test the shared MCP capability catalog contract."""

from draftpilot.core.capabilities import capabilities_for_page, capability_catalog


def test_catalog_contains_scoped_read_and_approved_mutation_capabilities() -> None:
    """Expose read capabilities while marking mutations for approval."""
    catalog = {capability.name: capability for capability in capability_catalog()}
    assert catalog["screenplay.read"].scope == "scene"
    assert catalog["timeline.propose"].mutates is False
    assert catalog["revisions.restore"].mutates is True
    assert catalog["revisions.restore"].approval_required is True
    assert catalog["context.generate"].mutates is False


def test_page_capabilities_are_server_authoritative() -> None:
    """Route each workflow page to only its typed capability bundle."""
    assert "timeline.propose" in capabilities_for_page("/projects/7/timeline")
    assert "outline.read" not in capabilities_for_page("/projects/7/timeline")
    assert capabilities_for_page("unknown") == ["screenplay.read", "context.read", "revisions.read"]


def test_capabilities_for_review_and_settings_cover_page_actions() -> None:
    """Expose proposal review and provider/backup actions on their owning pages."""
    review = capabilities_for_page("/projects/7/review")
    settings = capabilities_for_page("/settings")
    assert "screenplay.approve" in review
    assert "providers.write" in settings
    assert "backups.restore" in settings
