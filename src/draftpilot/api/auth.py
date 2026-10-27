"""REST API authentication dependency and browser session endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from draftpilot.core.api_auth import (
    SESSION_COOKIE,
    auth_required,
    issue_session,
    session_valid,
    token_matches,
)
from draftpilot.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


def is_authenticated(request: Request, credentials: HTTPAuthorizationCredentials | None) -> bool:
    """Return whether a request carries a valid bearer token or session cookie."""
    if not auth_required():
        return True
    if credentials is not None and credentials.scheme.casefold() == "bearer":
        return token_matches(credentials.credentials)
    cookie = request.cookies.get(SESSION_COOKIE)
    return cookie is not None and session_valid(cookie)


async def require_api_auth(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> None:
    """Reject unauthenticated requests when an API token is configured."""
    if not is_authenticated(request, credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="DraftPilot API authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthStatus(BaseModel):
    """Report whether the API needs a token and whether this browser holds a session."""

    auth_required: bool
    authenticated: bool


class SessionRequest(BaseModel):
    """Carry the API token submitted once from the browser sign-in form."""

    token: str = Field(min_length=1, max_length=500)


@router.get("/status", response_model=AuthStatus)
async def auth_status(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> AuthStatus:
    """Return the public authentication state used by the SPA before loading data."""
    return AuthStatus(auth_required=auth_required(), authenticated=is_authenticated(request, credentials))


@router.post("/session", response_model=AuthStatus)
async def create_session(data: SessionRequest, response: Response) -> AuthStatus:
    """Exchange the API token for an HttpOnly signed session cookie."""
    if not auth_required():
        return AuthStatus(auth_required=False, authenticated=True)
    if not token_matches(data.token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(),
        max_age=settings.api.session_max_age_seconds,
        httponly=True,
        samesite="strict",
        secure=settings.api.cookie_secure,
        path="/",
    )
    return AuthStatus(auth_required=True, authenticated=True)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(response: Response) -> None:
    """Sign the browser out by clearing its session cookie."""
    response.delete_cookie(SESSION_COOKIE, path="/")
