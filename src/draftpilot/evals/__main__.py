"""Run the room's eval suites on local LM Studio and compare them with the committed baselines.

    uv run python -m draftpilot.evals                   # every suite, compared with its baseline
    uv run python -m draftpilot.evals room_qa rewrite   # some suites
    uv run python -m draftpilot.evals --save-baseline   # record new baselines after a reviewed change
"""

import argparse
import asyncio
import sys

from draftpilot.evals.baseline import compare, save, summarize
from draftpilot.evals.harness import eval_models, eval_project
from draftpilot.evals.suites import SUITES


async def run(names: list[str], save_baseline: bool, tolerance: float) -> int:
    """Run each suite on a fresh eval project and return the number of regressions."""
    chat, chat_name, judge, judge_name = await eval_models()
    print(f"chat={chat_name} judge={judge_name}")
    regressions = 0
    for name in names:
        async with eval_project() as project:
            dataset, task = await SUITES[name].build(project, chat, chat_name, judge)
            report = await dataset.evaluate(task, max_concurrency=1, progress=False)
        report.print(include_input=False, include_output=False, include_durations=True)
        summary = summarize(name, report, chat_name, judge_name)
        if save_baseline:
            print(f"baseline saved: {save(summary)}")
            continue
        problems = compare(summary, tolerance)
        regressions += len(problems)
        print("\n".join(problems) if problems else f"{name}: no regression against baseline")
    return regressions


def main() -> None:
    """Parse arguments and exit non-zero on any regression."""
    parser = argparse.ArgumentParser(prog="python -m draftpilot.evals", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("suites", nargs="*", metavar="SUITE", help=f"suites to run (default: all of {', '.join(SUITES)})")
    parser.add_argument("--save-baseline", action="store_true", help="record the results as the new baselines")
    parser.add_argument("--tolerance", type=float, default=0.15, help="allowed drop in any average before it counts as a regression")
    args = parser.parse_args()
    unknown = sorted(set(args.suites) - set(SUITES))
    if unknown:
        parser.error(f"unknown suites {unknown}; choose from {', '.join(SUITES)}")
    sys.exit(1 if asyncio.run(run(args.suites or list(SUITES), args.save_baseline, args.tolerance)) else 0)


if __name__ == "__main__":
    main()
