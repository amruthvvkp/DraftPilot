"""Summarise eval reports and keep committed baselines so regressions fail loudly."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic_evals.reporting import EvaluationReport

from draftpilot.evals.evaluators import PRIMARY_JUDGE, SECOND_JUDGE

BASELINE_DIR = Path(__file__).resolve().parents[3] / "evals" / "baselines"


def _assertion_rate(cases: dict[str, Any]) -> float:
    """Return the share of passing assertions, leaving out the second judge so baselines stay comparable."""
    values = [value for case in cases.values() for name, value in case["assertions"].items() if name != SECOND_JUDGE]
    return round(sum(map(bool, values)) / len(values), 3) if values else 0.0


def agreement(cases: dict[str, Any], primary: str = PRIMARY_JUDGE, second: str = SECOND_JUDGE) -> dict[str, Any] | None:
    """Compare the two judges' verdicts case by case (``None`` when no case had both)."""
    both = {name: case for name, case in cases.items() if primary in case["assertions"] and second in case["assertions"]}
    if not both:
        return None
    split = {
        name: {"judge": case["assertions"][primary], "second_judge": case["assertions"][second], "reasons": case.get("reasons", {})}
        for name, case in both.items()
        if case["assertions"][primary] != case["assertions"][second]
    }
    return {"cases": len(both), "rate": round(1 - len(split) / len(both), 3), "disagreements": split}


def summarize(suite: str, report: EvaluationReport[Any, Any, Any], model: str, judge: str, second_judge: str = "") -> dict[str, Any]:
    """Reduce a report to comparable numbers: the assertion pass rate, score averages, per-case outcomes, judge agreement."""
    averages = report.averages()
    cases = {
        case.name: {
            "assertions": {name: result.value for name, result in case.assertions.items()},
            "failures": {name: result.reason for name, result in case.assertions.items() if not result.value and result.reason},
            "scores": {name: result.value for name, result in case.scores.items()},
            "metrics": case.metrics,
            "duration_s": round(case.task_duration, 1),
        }
        for case in report.cases
    }
    summary = {
        "suite": suite,
        "model": model,
        "judge": judge,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "cases": len(report.cases),
        "failures": [failure.name for failure in report.failures],
        "assertion_rate": _assertion_rate(cases),
        "scores": {name: round(value, 3) for name, value in (averages.scores if averages else {}).items()},
        "per_case": cases,
    }
    if second_judge:
        judged = {
            name: {**case, "reasons": {key: result.reason for key, result in report_case.assertions.items() if key in (PRIMARY_JUDGE, SECOND_JUDGE)}}
            for (name, case), report_case in zip(cases.items(), report.cases, strict=True)
        }
        summary["second_judge"] = second_judge
        summary["judge_agreement"] = agreement(judged)
    return summary


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


def notes(summary: dict[str, Any], directory: Path = BASELINE_DIR) -> list[str]:
    """Return informational lines: how the judges agreed, and whether the baseline was graded by another judge."""
    lines: list[str] = []
    split = summary.get("judge_agreement")
    if split:
        lines.append(f"{summary['suite']}: judges {summary['judge']} and {summary['second_judge']} agree on "
                     f"{split['cases'] - len(split['disagreements'])}/{split['cases']} cases")
        for case, verdicts in split["disagreements"].items():
            reasons = verdicts["reasons"]
            lines.append(f"  {case}: judge={verdicts['judge']} ({reasons.get(PRIMARY_JUDGE) or '-'}) "
                         f"second_judge={verdicts['second_judge']} ({reasons.get(SECOND_JUDGE) or '-'})")
    path = directory / f"{summary['suite']}.json"
    if path.exists():
        baseline = json.loads(path.read_text())
        if baseline.get("judge") and baseline["judge"] != summary["judge"]:
            lines.append(f"{summary['suite']}: baseline was judged by {baseline['judge']}, this run by {summary['judge']}; "
                         "judge-graded assertions may not be comparable")
    return lines
