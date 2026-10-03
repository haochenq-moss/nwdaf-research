#!/usr/bin/env python3
"""Evaluate verified external case telemetry, never exposure labels or live inputs."""

import argparse
import json
from pathlib import Path

from nwdaf_research.input_testing.anomaly_dataset import evaluate_anomaly_dataset, load_anomaly_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--analysis-plan", type=Path, required=True)
    parser.add_argument("--fit", action="store_true", help="Fit fixed baseline only after evidence checks pass")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite existing results")
    try:
        if args.fit:
            report = evaluate_anomaly_dataset(args.dataset, args.analysis_plan)
        else:
            verified = load_anomaly_dataset(args.dataset, args.analysis_plan)
            report = {"status": "DATASET_VERIFIED", "run_count": len(verified["rows"]),
                      "dataset_sha256": verified["dataset_sha256"], "inference_performed": False, "actionable": False}
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {"status": "BLOCKED", "reason": str(error), "model_fitted": False, "actionable": False}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report.get("status") == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())