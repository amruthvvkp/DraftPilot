"""Test provider profile response redaction and model boundaries."""

from datetime import UTC, datetime

from draftpilot.api.providers import _read
from draftpilot.models import ProviderProfile


def test_provider_read_never_contains_encrypted_credential() -> None:
    """Expose only credential presence, never the encrypted value."""
    profile = ProviderProfile(
        id=3,
        name="Local Ollama",
        provider="ollama",
        model="llama3.2",
        api_key_encrypted="encrypted-secret",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    response = _read(profile)
    assert response.has_api_key is True
    assert "encrypted-secret" not in response.model_dump_json()
