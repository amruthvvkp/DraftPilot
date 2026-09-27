"""Test the Temporal worker: run execution, retry budgets, bookkeeping, and job workflows."""

from types import SimpleNamespace
from typing import Any

from _async import run_async
from _temporal import temporal_worker
from temporalio import activity

from draftpilot.core import temporal
from draftpilot.worker import functions
from draftpilot.worker.workflows import WORKFLOWS, ExecuteRun


class _Ledger:
    """Record what the fake activities saw."""

    def __init__(self, failures: int = 0, max_attempts: int = 3, skip: str | None = None) -> None:
        """Configure how many attempts fail and the run's retry budget."""
        self.failures = failures
        self.max_attempts = max_attempts
        self.skip = skip
        self.attempts: list[int] = []
        self.finished: list[tuple[str, Any, Any]] = []
        self.workflow_ids: list[str] = []

    def activities(self) -> list[Any]:
        """Return fake activities registered under the real activity names."""

        @activity.defn(name="begin_run")
        async def begin_run(run_id: int, workflow_id: str) -> dict[str, object]:
            """Describe the run, or skip it."""
            self.workflow_ids.append(workflow_id)
            return {"skip": self.skip} if self.skip else {"kind": "evaluation", "max_attempts": self.max_attempts}

        @activity.defn(name="run_job")
        async def run_job(run_id: int) -> dict[str, Any]:
            """Fail the first ``failures`` attempts, then succeed."""
            attempt = activity.info().attempt
            self.attempts.append(attempt)
            if attempt <= self.failures:
                raise RuntimeError(f"provider offline on attempt {attempt}")
            return {"score": 0.9}

        @activity.defn(name="finish_run")
        async def finish_run(run_id: int, status: str, result: dict[str, Any] | None, error: str | None) -> None:
            """Record the terminal state."""
            self.finished.append((status, result, error))

        return [begin_run, run_job, finish_run]


async def _execute(ledger: _Ledger, run_id: int = 7) -> dict[str, Any]:
    """Run ExecuteRun against the fake activities and return its result."""
    async with temporal_worker([ExecuteRun], ledger.activities()) as (client, queue):
        return await client.execute_workflow(ExecuteRun.run, run_id, id=temporal.run_workflow_id(run_id), task_queue=queue)


def test_run_retries_within_its_attempt_budget_then_succeeds() -> None:
    """Retry a failing attempt through Temporal and mirror the success into Postgres."""
    ledger = _Ledger(failures=2, max_attempts=3)
    assert run_async(_execute(ledger)) == {"score": 0.9}
    assert ledger.attempts == [1, 2, 3]
    assert ledger.finished == [("succeeded", {"score": 0.9}, None)]
    assert ledger.workflow_ids == ["run-7"]


def test_run_fails_once_the_budget_is_spent() -> None:
    """Stop at the run's ``max_attempts`` and record the last error."""
    ledger = _Ledger(failures=5, max_attempts=2)
    result = run_async(_execute(ledger))
    assert result["status"] == "failed"
    assert "provider offline on attempt 2" in result["error"]
    assert ledger.attempts == [1, 2]
    assert ledger.finished[0][0] == "failed"


def test_terminal_runs_are_not_executed_again() -> None:
    """Skip a run that is already cancelled or succeeded."""
    ledger = _Ledger(skip="cancelled")
    assert run_async(_execute(ledger)) == {"status": "cancelled"}
    assert ledger.attempts == []
    assert ledger.finished == []


def test_every_job_the_web_starts_has_a_workflow() -> None:
    """Keep the start-by-name job types in step with the registered workflows."""
    names = {getattr(workflow, "__temporal_workflow_definition").name for workflow in WORKFLOWS}
    assert names == {
        "index_rag_document",
        "delete_rag_document",
        "reindex_project",
        "refresh_story_twin",
        "purge_rag_project",
        temporal.RUN_WORKFLOW,
    }


class _Session:
    """Capture writes for the isolated job test."""

    def add(self, value: object) -> None:
        """Accept one persisted model."""

    async def commit(self) -> None:
        """Accept one commit."""

    async def refresh(self, value: object) -> None:
        """Accept one refresh."""


class _SessionScope:
    """Provide an async context manager around the fake session."""

    async def __aenter__(self) -> _Session:
        """Return the isolated session."""
        return _Session()

    async def __aexit__(self, *args: object) -> None:
        """Close the isolated session context."""


def test_failed_attempt_is_recorded_before_temporal_retries(monkeypatch) -> None:
    """Annotate the run with the attempt's error so the UI shows why it is retrying."""
    run = SimpleNamespace(id=23, kind="evaluation", status="running", attempt_count=0, max_attempts=3, input={"screenplay_id": 1}, error=None)

    async def get(_session: object, _run_id: int) -> object:
        """Return the fake run."""
        return run

    async def update_status(_session: object, current: Any, status: str, result: object = None, error: str | None = None) -> object:
        """Apply the transition to the fake run."""
        current.status, current.error = status, error
        return current

    async def evaluate(_run: object) -> dict[str, object]:
        """Fail like an unreachable provider."""
        raise RuntimeError("provider offline")

    monkeypatch.setattr(functions, "session_scope", _SessionScope)
    monkeypatch.setattr(functions.workflow_runs_crud, "get", get)
    monkeypatch.setattr(functions.workflow_runs_crud, "update_status", update_status)
    monkeypatch.setattr(functions, "evaluate_screenplay", evaluate)

    try:
        run_async(functions.run_job(23, 1))
    except RuntimeError as exc:
        assert str(exc) == "provider offline"
    else:
        raise AssertionError("the attempt should fail so Temporal retries it")
    assert run.attempt_count == 1
    assert run.status == "running"
    assert run.error == "Attempt 1/3 failed: provider offline"


def test_start_helpers_collapse_duplicate_runs(monkeypatch) -> None:
    """Start a run under its stable id and join an already-running one."""
    calls: list[dict[str, Any]] = []

    class _Client:
        """Capture start_workflow calls."""

        async def start_workflow(self, workflow: str, **options: Any) -> None:
            """Record the call."""
            calls.append({"workflow": workflow, **options})

    async def get_client() -> _Client:
        """Return the fake client."""
        return _Client()

    monkeypatch.setattr(temporal, "get_client", get_client)
    assert run_async(temporal.start_run(12)) == "run-12"
    assert calls[0]["workflow"] == "execute_workflow"
    assert calls[0]["args"] == [12]
    assert calls[0]["id_conflict_policy"].name == "USE_EXISTING"
    assert run_async(temporal.start_best_effort("reindex_project", 3, description="reindex")) is True
    assert calls[1]["id_conflict_policy"].name == "FAIL"


def test_best_effort_start_survives_an_absent_server() -> None:
    """Log and carry on when Temporal is unreachable (the autouse fixture removes it)."""
    assert run_async(temporal.start_best_effort("reindex_project", 3, description="reindex")) is False
