"""Test worker lifecycle recovery without Redis or Postgres."""

from types import SimpleNamespace

from _async import run_async
from draftpilot.worker import settings as worker_settings


class _Session:
    """Capture lifecycle writes for the isolated worker test."""

    def __init__(self) -> None:
        """Initialize the captured session state."""
        self.added: list[object] = []
        self.commits = 0

    def add(self, value: object) -> None:
        """Capture one persisted model."""
        self.added.append(value)

    async def commit(self) -> None:
        """Count one transaction commit."""
        self.commits += 1


class _SessionScope:
    """Provide an async context manager around the fake session."""

    def __init__(self, session: _Session) -> None:
        """Store the session returned by the context manager."""
        self.session = session

    async def __aenter__(self) -> _Session:
        """Return the isolated session."""
        return self.session

    async def __aexit__(self, *args: object) -> None:
        """Close the isolated session context."""
        return None


class _Pool:
    """Capture jobs requeued during worker startup."""

    def __init__(self) -> None:
        """Initialize the captured job list."""
        self.jobs: list[tuple[str, int]] = []

    async def enqueue_job(self, name: str, run_id: int) -> None:
        """Capture one durable workflow job."""
        self.jobs.append((name, run_id))


def test_startup_requeues_interrupted_runs(monkeypatch) -> None:
    """Requeue running runs and preserve an explicit restart diagnostic."""
    session = _Session()
    pool = _Pool()
    interrupted = [SimpleNamespace(id=17, status="running", error=None)]
    monkeypatch.setattr(worker_settings.telemetry, "setup", lambda **_: None)
    monkeypatch.setattr(worker_settings, "session_scope", lambda: _SessionScope(session))
    monkeypatch.setattr(worker_settings.workflow_runs_crud, "list_interrupted", lambda _: _runs(interrupted))
    monkeypatch.setattr(worker_settings, "get_arq_pool", lambda: _pool(pool))

    run_async(worker_settings.startup({}))

    assert interrupted[0].status == "queued"
    assert interrupted[0].error == "Requeued after worker restart"
    assert session.commits == 1
    assert pool.jobs == [("execute_workflow", 17)]


async def _runs(runs: list[object]) -> list[object]:
    """Return fake interrupted runs from an async CRUD boundary."""
    return runs


async def _pool(pool: _Pool) -> _Pool:
    """Return the fake queue pool from an async boundary."""
    return pool
