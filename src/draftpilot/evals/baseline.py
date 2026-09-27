"""Summarise eval reports and keep committed baselines so regressions fail loudly."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic_evals.reporting import EvaluationReport

BASELINE_DIR = Path(__file__).resolve().parents[3] / "evals" / "baselines"


def summarize(suite: str, report: EvaluationReport[Any, Any, Any], model: str, judge: str) -> dict[str, Any]:
    """Reduce a report to comparable numbers: the assertion pass rate, score averages, and per-case outcomes."""
    averages = report.averages()
    cases = {
        case.name: {
            "assertions": {name: result.value for name, result in case.assertions.items()},
            "scores": {name: result.value for name, result in case.scores.items()},
            "metrics": case.metrics,
            "duration_s": round(case.task_duration, 1),
        }
        for case in report.cases
    }
    return {
        "suite": suite,
        "model": model,
        "judge": judge,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "cases": len(report.cases),
        "failures": [failure.name for failure in report.failures],
        "assertion_rate": round(averages.assertions, 3) if averages and averages.assertions is not None else 0.0,
        "scores": {name: round(value, 3) for name, value in (averages.scores if averages else {}).items()},
        "per_case": cases,
    }


def save(summary: dict[str, Any], directory: Path = BASELINE_DIR) -> Path:
    """Write a suite's summary as its baseline."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{summary['suite']}.json"
    path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
    return path


def compare(summary: dict[str, Any], tolerance: float, directory: Path = BASELINE_DIR) -> list[str]:
    """Return the ways a run is worse than its baseline (empty when there is no baseline yet)."""
    path = directory / f"{summary['suite']}.json"
    if not path.exists():
        return []
    baseline = json.loads(path.read_text())
    problems: list[str] = []
    if summary["failures"]:
        problems.append(f"{summary['suite']}: task failures {summary['failures']}")
    if summary["assertion_rate"] < baseline["assertion_rate"] - tolerance:
        problems.append(f"{summary['suite']}: assertion rate {summary['assertion_rate']} < baseline {baseline['assertion_rate']}")
    for name, value in baseline.get("scores", {}).items():
        current = summary["scores"].get(name)
        if current is not None and current < value - tolerance:
            problems.append(f"{summary['suite']}: {name} {current} < baseline {value}")
    return problems
