"""Test project bootstrap persistence behavior."""

from typing import Any

from _async import run_async

from draftpilot.crud.projects import create_with_references
from draftpilot.models import Act, Project, ProjectCreate, Screenplay


class _Session:
    """Capture objects added by the project bootstrap transaction."""

    def __init__(self) -> None:
        """Initialize the isolated object store."""
        self.added: list[Any] = []

    def add(self, value: Any) -> None:
        """Capture one pending model."""
        self.added.append(value)

    async def flush(self) -> None:
        """Assign identifiers required by dependent bootstrap records."""
        for value in self.added:
            if isinstance(value, Project) and value.id is None:
                value.id = 9
            if isinstance(value, Screenplay) and value.id is None:
                value.id = 12

    async def commit(self) -> None:
        """Complete the isolated transaction."""

    async def refresh(self, _value: Any) -> None:
        """Refresh no-op test fixtures."""


def test_project_creation_bootstraps_screenplay_and_first_act() -> None:
    """Create a usable screenplay workspace with every new project."""
    session = _Session()
    project = run_async(create_with_references(session, ProjectCreate(title="Lantern", languages=[], genres=[]), []))
    screenplays = [value for value in session.added if isinstance(value, Screenplay)]
    acts = [value for value in session.added if isinstance(value, Act)]
    assert project.id == 9
    assert len(screenplays) == 1
    assert screenplays[0].title == "Lantern"
    assert len(acts) == 1
    assert acts[0].screenplay_id == 12
    assert acts[0].title == "Act One"
