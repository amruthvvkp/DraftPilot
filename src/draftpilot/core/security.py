"""Security helpers for encrypting credentials before persistence."""

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr


def _fernet(master_key: SecretStr) -> Fernet:
    """Build an encryptor from a configured Fernet key."""
    key = master_key.get_secret_value()
    if not key:
        raise ValueError("SECRETS__MASTER_KEY must be configured")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise ValueError("SECRETS__MASTER_KEY must be a valid Fernet key") from exc


def encrypt_secret(value: str, master_key: SecretStr) -> str:
    """Encrypt a provider credential into a persistable token."""
    return _fernet(master_key).encrypt(value.encode()).decode()


def decrypt_secret(token: str, master_key: SecretStr) -> str:
    """Decrypt a persisted provider credential or reject tampering."""
    try:
        return _fernet(master_key).decrypt(token.encode()).decode()
    except (InvalidToken, UnicodeDecodeError, ValueError, TypeError) as exc:
        raise ValueError("Unable to decrypt provider credential") from exc
