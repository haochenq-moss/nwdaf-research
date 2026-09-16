#!/usr/bin/env python3
"""Summarize real network telemetry in the supplemental derived dataset."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from nwdaf_research.preprocessing.features import RunFeatureBuilder


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/supplemental_raw"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/supplemental_telemetry.json"))
    args = parser.parse_args()
    builder = RunFeatureBuilder(args.root)
    rows = []
    scenarios = Counter()
    for run_dir in sorted(builder.raw_root.glob("R*")):
        if not run_dir.is_dir():
            continue
        features = builder.build_features_for_run(run_dir.name)
        scenarios[features.get("scenario_id", "unknown")] += 1
        rows.append(
            {
                "run_id": run_dir.name,
                "scenario_id": features.get("scenario_id"),
                "sbi_event_count": features["sbi_event_count"],
                "pfcp_event_count": features["pfcp_event_count"],
                "sbi_error_event_count": features["sbi_error_event_count"],
                "pfcp_request_count": features["pfcp_request_count"],
                "pfcp_response_count": features["pfcp_response_count"],
                "sbi_telemetry_available": features["sbi_telemetry_available"],
                "pfcp_telemetry_available": features["pfcp_telemetry_available"],
            }
        )
    report = {
        "run_count": len(rows),
        "scenario_counts": dict(scenarios),
        "total_sbi_events": sum(row["sbi_event_count"] for row in rows),
        "total_pfcp_events": sum(row["pfcp_event_count"] for row in rows),
        "runs_with_sbi": sum(row["sbi_telemetry_available"] for row in rows),
        "runs_with_pfcp": sum(row["pfcp_telemetry_available"] for row in rows),
        "runs": rows,
        "source": "Ubuntu free5GC supplemental_raw archive",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()