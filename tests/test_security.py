"""Test provider credential encryption boundaries."""

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from draftpilot.core.security import decrypt_secret, encrypt_secret


def test_secret_round_trip_does_not_store_plaintext() -> None:
    """Encrypt and decrypt a provider credential with a valid master key."""
    key = SecretStr(Fernet.generate_key().decode())
    token = encrypt_secret("provider-token", key)
    assert token != "provider-token"
    assert decrypt_secret(token, key) == "provider-token"


def test_secret_operations_reject_missing_or_wrong_key() -> None:
    """Refuse unusable keys and tokens encrypted by another key."""
    key = SecretStr(Fernet.generate_key().decode())
    with pytest.raises(ValueError, match="MASTER_KEY"):
        encrypt_secret("token", SecretStr(""))
    token = encrypt_secret("token", key)
    with pytest.raises(ValueError, match="Unable to decrypt"):
        decrypt_secret(token, SecretStr(Fernet.generate_key().decode()))
