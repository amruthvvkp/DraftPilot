"""Authentication primitives shared by DraftPilot MCP transports."""

import hmac

from pydantic import SecretStr


def valid_static_token(provided: str, expected: str) -> bool:
    """Compare a bearer token without leaking timing information."""
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())


def client_id_for_token(
    token: str, default_token: str, client_tokens: dict[str, SecretStr]
) -> str | None:
    """Resolve a bearer token to its registered client identity."""
    if valid_static_token(token, default_token):
        return "mcp-client"
    for client_id, configured in client_tokens.items():
        if valid_static_token(token, configured.get_secret_value()):
            return client_id
    return None
