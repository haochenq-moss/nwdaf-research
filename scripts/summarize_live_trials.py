#!/usr/bin/env python3
"""Summarize persisted live B0/B1/B2 trial reports without causal overclaiming."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def values(reports: list[dict[str, Any]], path: tuple[str, ...]) -> list[float]:
    result: list[float] = []
    for report in reports:
        current: Any = report
        try:
            for key in path:
                current = current[key]
            if isinstance(current, (int, float)):
                result.append(float(current))
        except (KeyError, TypeError):
            continue
    return result


def summarize(series: list[float]) -> dict[str, Any]:
    if not series:
        return {"count": 0, "status": "unavailable"}
    result: dict[str, Any] = {
        "count": len(series),
        "mean": statistics.fmean(series),
        "median": statistics.median(series),
        "min": min(series),
        "max": max(series),
    }
    result["stddev"] = statistics.stdev(series) if len(series) > 1 else 0.0
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--b0", type=Path, nargs="*", default=[])
    parser.add_argument("--b2", type=Path, nargs="*", default=[])
    parser.add_argument("--output", type=Path, default=Path("evaluation/live_trial_summary.json"))
    args = parser.parse_args()

    b0_reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.b0]
    b2_reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.b2]
    report = {
        "b0_trials": len(b0_reports),
        "b2_trials": len(b2_reports),
        "B0": {
            "rtt_mean_ms": summarize(values(b0_reports, ("measurement", "rtt_mean_ms"))),
            "packet_loss_percent": summarize(values(b0_reports, ("measurement", "packet_loss_percent"))),
            "throughput_sent_bps": summarize(values(b0_reports, ("measurement", "throughput", "sent_bps"))),
            "throughput_received_bps": summarize(values(b0_reports, ("measurement", "throughput", "received_bps"))),
        },
        "B2_alert_only": {
            "detection_latency_ms": summarize(values(b2_reports, ("detection_latency_ms",))),
            "mitigation_latency_ms": summarize(values(b2_reports, ("mitigation_latency_ms",))),
            "before_rtt_mean_ms": summarize(values(b2_reports, ("before", "network", "rtt_mean_ms"))),
            "after_rtt_mean_ms": summarize(values(b2_reports, ("after", "network", "rtt_mean_ms"))),
            "before_packet_loss_percent": summarize(values(b2_reports, ("before", "network", "packet_loss_percent"))),
            "after_packet_loss_percent": summarize(values(b2_reports, ("after", "network", "packet_loss_percent"))),
            "interpretation": "alert_operator does not change network state; recovery cannot be attributed to this action",
        },
        "limitations": [
            "B0 and B2 trials are sequential, not randomized",
            "B2 uses alert_operator only; tc rate_limit remains disabled",
            "Network differences are descriptive and not causal mitigation evidence",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()