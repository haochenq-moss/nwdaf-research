#!/usr/bin/env python3
"""Generate a conservative paper-ready summary from measured artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def metric(report: dict, config: str, name: str) -> dict:
    return report[config][name]


def fmt(values: dict, digits: int = 4) -> str:
    if values.get("status") == "unavailable":
        return "unavailable"
    return f"{values['mean']:.{digits}f} +/- {values['stddev']:.{digits}f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, default=Path("evaluation/configuration_trials_summary.json"))
    parser.add_argument("--b2", type=Path, default=Path("evaluation/b2_alert_trial.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/paper_results.md"))
    args = parser.parse_args()

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    b2 = json.loads(args.b2.read_text(encoding="utf-8")) if args.b2.exists() else None
    b0 = summary["B0"]
    b1 = summary["B1"]
    lines = [
        "# Measured Live Results",
        "",
        "This report is generated from measured artifacts and does not claim causal mitigation benefit.",
        "",
        "## B0/B1 Repeated Trials",
        "",
        f"Number of sequential trials: {summary['trial_count']}",
        "",
        "| Metric | B0 | B1 |",
        "| --- | ---: | ---: |",
        f"| RTT mean (ms) | {fmt(metric(summary, 'B0', 'rtt_mean_ms'))} | {fmt(metric(summary, 'B1', 'rtt_mean_ms'))} |",
        f"| Packet loss (%) | {fmt(metric(summary, 'B0', 'packet_loss_percent'))} | {fmt(metric(summary, 'B1', 'packet_loss_percent'))} |",
        f"| Throughput sent (bit/s) | {fmt(metric(summary, 'B0', 'throughput_sent_bps'))} | {fmt(metric(summary, 'B1', 'throughput_sent_bps'))} |",
        f"| Throughput received (bit/s) | {fmt(metric(summary, 'B0', 'throughput_received_bps'))} | {fmt(metric(summary, 'B1', 'throughput_received_bps'))} |",
        f"| Detection latency (ms) | not applicable | {fmt(b1['detection_latency_ms'])} |",
        "",
        "Throughput was measured on the local `ueTun0` to Ubuntu-host path. The sequential design does not support a causal claim that B1 changed network performance.",
        "",
        "## B2 Alert-Only Trial",
        "",
    ]
    if b2 is None:
        lines.append("No B2 alert-only artifact was available.")
    else:
        lines.extend(
            [
                f"Decision: `{b2['decision_id']}`; prediction: `{b2['detection']['predicted_label']}` with probability `{b2['detection']['anomaly_probability']:.3f}`.",
                f"Detection latency: `{b2['detection_latency_ms']:.2f} ms`; response latency: `{b2['mitigation_latency_ms']:.2f} ms`.",
                f"Before/after RTT: `{b2['before']['network']['rtt_mean_ms']:.3f}` / `{b2['after']['network']['rtt_mean_ms']:.3f} ms`; packet loss remained `{b2['before']['network']['packet_loss_percent']}%` / `{b2['after']['network']['packet_loss_percent']}%`.",
                "The action was `alert_operator`, which does not alter network state. These before/after values therefore do not establish recovery caused by mitigation.",
            ]
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- B0/B1 trials were sequential rather than randomized.",
            "- B2 has one alert-only trial; repeated B2 trials are needed for uncertainty estimates.",
            "- `tc` rate limiting remains disabled because Ubuntu requires an interactive sudo password.",
            "- No causal recovery, availability improvement, or mitigation effectiveness claim is made.",
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()