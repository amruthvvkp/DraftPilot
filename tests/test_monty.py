"""Test Monty feature gating and capability boundaries."""

import pytest
from _async import run_async

from draftpilot.core.config import MontySettings
from draftpilot.core.monty import (
    MontyDisabledError,
    MontyExecutionConfig,
    MontySandboxError,
    audit_record,
    execute_glue,
    execute_glue_audited,
    execution_config,
)
from draftpilot.models import MontyExecutionCreate


def test_monty_is_disabled_by_default() -> None:
    """Reject model code unless an explicit feature flag is supplied."""
    with pytest.raises(MontyDisabledError):
        execute_glue("1 + 1")


def test_monty_runs_bounded_typed_glue_without_host_bridges() -> None:
    """Run typed arithmetic and reject ambient filesystem access."""
    config = MontyExecutionConfig(enabled=True, max_duration_seconds=1)
    result = execute_glue("total + 2", {"total": 3}, config)
    assert result.value == 5
    assert execute_glue("x: int = 3\nx + 2", config=config).value == 5
    with pytest.raises(MontySandboxError):
        execute_glue("open('secret.txt')", config=config)


def test_monty_rejects_oversized_code_and_inputs() -> None:
    """Enforce code and input bounds before starting a worker."""
    config = MontyExecutionConfig(enabled=True, max_code_chars=3, max_input_items=1)
    with pytest.raises(MontySandboxError):
        execute_glue("1 + 1", config=config)
    with pytest.raises(MontySandboxError):
        execute_glue("1", {"a": 1, "b": 2}, config)


def test_monty_settings_are_translated_without_widening_limits() -> None:
    """Translate the environment-backed feature gate and limits exactly."""
    config = execution_config(MontySettings(enabled=True, max_code_chars=10, max_input_items=2))
    assert config.enabled is True
    assert config.max_code_chars == 10
    assert config.max_input_items == 2


def test_monty_audit_payload_redacts_code_and_inputs() -> None:
    """Create a bounded audit payload without retaining sensitive execution values."""
    result = audit_record(7, "secret = 1", {"token": "private"}, error="failed")
    assert result.project_id == 7
    assert result.status == "failed"
    assert result.code_sha256
    assert result.input_count == 1
    assert result.error == "failed"
    assert "secret" not in result.model_dump_json()
    assert "private" not in result.model_dump_json()


def test_audited_monty_execution_persists_redacted_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Persist bounded audit records for successful and rejected execution."""
    records: list[MontyExecutionCreate] = []

    async def capture(_session: object, data: MontyExecutionCreate) -> MontyExecutionCreate:
        """Capture the CRUD payload without requiring a database."""
        records.append(data)
        return data

    monkeypatch.setattr("draftpilot.crud.monty_executions.create", capture)
    config = MontyExecutionConfig(enabled=True, max_duration_seconds=1)
    result = run_async(execute_glue_audited(object(), 7, "total + 2", {"total": 3}, config, 11))

    assert result.value == 5
    assert records[0].status == "completed"
    assert records[0].run_id == 11
    assert records[0].input_count == 1
    assert "total + 2" not in records[0].model_dump_json()

    with pytest.raises(MontySandboxError):
        run_async(execute_glue_audited(object(), 7, "open('private')", config=config, run_id=12))
    assert records[1].status == "failed"
    assert records[1].run_id == 12
    assert "private" not in records[1].model_dump_json()
