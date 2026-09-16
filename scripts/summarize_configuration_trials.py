#!/usr/bin/env python3
"""Summarize repeated live B0/B1 configuration reports for research use."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def series(reports: list[dict[str, Any]], *path: str) -> list[float]:
    output: list[float] = []
    for report in reports:
        value: Any = report
        try:
            for key in path:
                value = value[key]
            if isinstance(value, (int, float)):
                output.append(float(value))
        except (KeyError, TypeError):
            continue
    return output


def summarize(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "status": "unavailable"}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "stddev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, default=Path("evaluation/configuration_trials_summary.json"))
    args = parser.parse_args()
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]

    def network(config: str) -> dict[str, Any]:
        root = (config, "network_measurement")
        return {
            "rtt_mean_ms": summarize(series(reports, *root, "rtt_mean_ms")),
            "packet_loss_percent": summarize(series(reports, *root, "packet_loss_percent")),
            "throughput_sent_bps": summarize(series(reports, *root, "throughput", "sent_bps")),
            "throughput_received_bps": summarize(series(reports, *root, "throughput", "received_bps")),
        }

    report = {
        "trial_count": len(reports),
        "B0": network("B0"),
        "B1": {
            **network("B1"),
            "detection_latency_ms": summarize(series(reports, "B1", "detection_latency_ms")),
        },
        "B2": {
            "status": "not included in this report",
            "reason": "Use the alert-only B2 trial runner and summarize its persisted reports separately.",
        },
        "interpretation": "Sequential live measurements are descriptive and do not establish causal mitigation benefit.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()