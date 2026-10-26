"""Domain errors shared by the REST API and the MCP server.

Each error is an HTTP exception, so a REST route can let it propagate and FastAPI answers with
its status and detail; the MCP server converts it into a tool error with the same message.
"""

from http import HTTPStatus

from starlette.exceptions import HTTPException


class DomainError(HTTPException):
    """A rejected domain operation, carrying the HTTP status it maps to."""

    status = HTTPStatus.BAD_REQUEST

    def __init__(self, detail: str) -> None:
        """Create the error with a writer-readable message."""
        super().__init__(status_code=int(self.status), detail=detail)


class NotFound(DomainError):
    """The target does not exist in the requested project."""

    status = HTTPStatus.NOT_FOUND


class Forbidden(DomainError):
    """The caller's scope or permission mode does not allow the operation."""

    status = HTTPStatus.FORBIDDEN


class Conflict(DomainError):
    """The target changed since the caller read it, or the operation clashes with its state."""

    status = HTTPStatus.CONFLICT


class Invalid(DomainError):
    """The request is well-formed but semantically invalid."""

    status = HTTPStatus.UNPROCESSABLE_CONTENT


class PreconditionRequired(DomainError):
    """The caller must send the version it last read (``If-Match``)."""

    status = HTTPStatus.PRECONDITION_REQUIRED


def check_version(expected: int | None, current: int, what: str, *, required: bool = True) -> None:
    """Enforce optimistic concurrency: require the caller's version and reject a stale one."""
    if expected is None:
        if required:
            raise PreconditionRequired("If-Match is required")
        return
    if expected != current:
        raise Conflict(f"{what} has changed")
