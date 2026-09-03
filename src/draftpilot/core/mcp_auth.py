"""Authentication primitives shared by DraftPilot MCP transports."""

import hmac


def valid_static_token(provided: str, expected: str) -> bool:
    """Compare a bearer token without leaking timing information."""
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())
