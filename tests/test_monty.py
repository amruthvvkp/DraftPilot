"""Test Monty feature gating and capability boundaries."""

import pytest

from draftpilot.core.config import MontySettings
from draftpilot.core.monty import MontyDisabledError, MontyExecutionConfig, MontySandboxError, execute_glue, execution_config


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
