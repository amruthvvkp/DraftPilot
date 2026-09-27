"""Single-user REST API authentication: bearer token or signed session cookie."""

import hashlib
import hmac
import time

from draftpilot.core.config import settings

SESSION_COOKIE = "draftpilot_session"
_SESSION_CONTEXT = b"draftpilot-session:v1:"


def auth_required() -> bool:
    """Return whether the REST API is protected by a configured token."""
    return bool(settings.api.token.get_secret_value())


def token_matches(candidate: str) -> bool:
    """Compare a presented token with the configured API token in constant time."""
    expected = settings.api.token.get_secret_value()
    return bool(expected) and hmac.compare_digest(candidate.encode(), expected.encode())


def _signature(issued_at: int) -> str:
    """Sign a session issue time with a key derived from the API token."""
    key = hashlib.sha256(_SESSION_CONTEXT + settings.api.token.get_secret_value().encode()).digest()
    return hmac.new(key, str(issued_at).encode(), hashlib.sha256).hexdigest()


def issue_session(now: float | None = None) -> str:
    """Return a signed session cookie value; rotating the token invalidates it."""
    issued_at = int(now if now is not None else time.time())
    return f"{issued_at}.{_signature(issued_at)}"


def session_valid(value: str, now: float | None = None) -> bool:
    """Return whether a session cookie is well-formed, correctly signed, and unexpired."""
    if not auth_required():
        return False
    issued_raw, _, signature = value.partition(".")
    if not issued_raw.isdigit() or not signature:
        return False
    issued_at = int(issued_raw)
    current = now if now is not None else time.time()
    if issued_at > current + 60 or current - issued_at > settings.api.session_max_age_seconds:
        return False
    return hmac.compare_digest(signature, _signature(issued_at))


def open_api_warning(host: str) -> str | None:
    """Return a warning when the API is unauthenticated on a non-loopback bind address."""
    if auth_required() or host in {"127.0.0.1", "localhost", "::1"}:
        return None
    return (
        f"DraftPilot API is bound to {host} without API__TOKEN: anyone who can reach this port "
        "can read and change every project. Set API__TOKEN for any non-local use."
    )
