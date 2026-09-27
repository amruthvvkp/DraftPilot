"""Compare two fixture-backed DraftPilot benchmark manifests."""

import argparse
import json
from pathlib import Path

from draftpilot.core.benchmark import BenchmarkManifest, compare_manifests


def _read_manifest(path: Path) -> BenchmarkManifest:
    """Read and validate one benchmark manifest from JSON."""
    return BenchmarkManifest.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> None:
    """Compare control and candidate manifests and print a JSON report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    report = compare_manifests(_read_manifest(args.control), _read_manifest(args.candidate))
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
