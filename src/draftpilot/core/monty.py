"""Run tightly bounded model-generated glue code through Pydantic Monty."""

from dataclasses import dataclass
from hashlib import sha256
from time import monotonic
from typing import Any

import logfire
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.config import MontySettings
from draftpilot.models import MontyExecutionCreate


class MontyDisabledError(RuntimeError):
    """Signal that feature-gated Monty execution is disabled."""


class MontySandboxError(RuntimeError):
    """Signal rejected or failed sandbox execution."""


@dataclass(frozen=True)
class MontyExecutionConfig:
    """Bound the code, runtime, and output permitted for one execution."""

    enabled: bool = False
    max_code_chars: int = 20_000
    max_input_items: int = 100
    max_duration_seconds: float = 0.5
    max_output_chars: int = 20_000


@dataclass(frozen=True)
class MontyExecutionResult:
    """Return bounded sandbox output and elapsed execution time."""

    value: Any
    stdout: str
    duration_ms: int


def audit_record(
    project_id: int,
    code: str,
    inputs: dict[str, Any] | None,
    result: MontyExecutionResult | None = None,
    run_id: int | None = None,
    error: str | None = None,
) -> MontyExecutionCreate:
    """Build a redacted persistence payload for one Monty attempt."""
    return MontyExecutionCreate(
        project_id=project_id,
        run_id=run_id,
        status="completed" if result is not None and error is None else "failed",
        code_sha256=sha256(code.encode("utf-8")).hexdigest(),
        input_count=len(inputs or {}),
        output_chars=len(result.stdout) if result is not None else 0,
        duration_ms=result.duration_ms if result is not None else 0,
        error=error[:1000] if error else None,
    )


def execution_config(settings: MontySettings) -> MontyExecutionConfig:
    """Convert application settings into bounded execution configuration."""
    return MontyExecutionConfig(
        enabled=settings.enabled,
        max_code_chars=settings.max_code_chars,
        max_input_items=settings.max_input_items,
        max_duration_seconds=settings.max_duration_seconds,
        max_output_chars=settings.max_output_chars,
    )


def execute_glue(
    code: str,
    inputs: dict[str, Any] | None = None,
    config: MontyExecutionConfig | None = None,
) -> MontyExecutionResult:
    """Execute code with Monty and no ambient host capabilities."""
    effective = config or MontyExecutionConfig()
    if not effective.enabled:
        raise MontyDisabledError("Monty execution is disabled")
    if not code.strip() or len(code) > effective.max_code_chars:
        raise MontySandboxError("Code is empty or exceeds the configured limit")
    values = inputs or {}
    if len(values) > effective.max_input_items:
        raise MontySandboxError("Input count exceeds the configured limit")
    try:
        from pydantic_monty import Monty, ResourceLimits

        output: list[str] = []

        def capture_stdout(channel: str, text: str) -> None:
            """Capture only bounded stdout emitted by the sandbox."""
            if channel != "stdout":
                return
            output.append(text)
            if sum(len(item) for item in output) > effective.max_output_chars:
                raise MontySandboxError("Sandbox output exceeds the configured limit")

        started = monotonic()
        with (
            Monty(request_timeout=effective.max_duration_seconds) as pool,
            pool.checkout(
                limits=ResourceLimits(max_feed_duration_secs=effective.max_duration_seconds),
                type_check=not values,
            ) as session,
        ):
            value = session.feed_run(code, inputs=values, print_callback=capture_stdout)
        duration_ms = round((monotonic() - started) * 1000)
        logfire.info("Monty glue execution completed in {duration_ms}ms", duration_ms=duration_ms)
        return MontyExecutionResult(value=value, stdout="".join(output), duration_ms=duration_ms)
    except MontySandboxError:
        raise
    except Exception as exc:
        raise MontySandboxError("Monty execution failed") from exc


async def execute_glue_audited(
    session: AsyncSession,
    project_id: int,
    code: str,
    inputs: dict[str, Any] | None = None,
    config: MontyExecutionConfig | None = None,
    run_id: int | None = None,
) -> MontyExecutionResult:
    """Execute bounded glue and persist a redacted success or failure audit."""
    from draftpilot.crud import monty_executions as executions_crud

    try:
        result = execute_glue(code, inputs, config)
    except (MontyDisabledError, MontySandboxError) as exc:
        await executions_crud.create(
            session,
            audit_record(project_id, code, inputs, run_id=run_id, error=str(exc)),
        )
        raise
    await executions_crud.create(
        session, audit_record(project_id, code, inputs, result=result, run_id=run_id)
    )
    return result
