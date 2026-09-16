#!/usr/bin/env python3
"""Measure live B0/B1/B2 observables without fabricating response effects."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer
from nwdaf_research.live.benchmark import SSHBaselineBenchmark
from nwdaf_research.live.ssh_observer import SSHLiveObserver


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2222)
    parser.add_argument("--user", default="haochenqin-moss")
    parser.add_argument("--identity-file", default="~/.ssh/id_ecdsa")
    parser.add_argument("--target", default="10.60.0.1")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("evaluation/live_configurations.json"))
    args = parser.parse_args()

    benchmark = SSHBaselineBenchmark(
        host=args.host, port=args.port, user=args.user, identity_file=args.identity_file
    )
    analyzer = NWDAFResearchAnalyzer(args.raw_root, model_artifact="models/rf-v1")

    b0_start = time.perf_counter()
    b0 = benchmark.measure(target=args.target, count=args.count)
    b0_elapsed_ms = (time.perf_counter() - b0_start) * 1000

    observer = SSHLiveObserver(
        host=args.host, port=args.port, user=args.user, identity_file=args.identity_file
    )
    observation = observer.observe()
    inference_start = time.perf_counter()
    analytics = analyzer.score_features(observation.features)
    inference_elapsed_ms = (time.perf_counter() - inference_start) * 1000

    b1 = {
        "detection": analytics,
        "detection_latency_ms": inference_elapsed_ms,
        "network_measurement": benchmark.measure(target=args.target, count=args.count).as_dict(),
    }
    b2_network = benchmark.measure(target=args.target, count=args.count)
    b2 = {
        "response_status": "skipped",
        "reason": "single live snapshot is not autonomous-response eligible",
        "autonomous_response_eligible": observation.complete_for_autonomous_response,
        "mitigation_latency_ms": "unavailable",
        "recovery_time": "unavailable",
        "network_measurement": b2_network.as_dict(),
    }
    report = {
        "target": args.target,
        "measurement_scope": "same live UE target; sequential observations",
        "B0": {"network_measurement": b0.as_dict(), "measurement_overhead_ms": b0_elapsed_ms},
        "B1": b1,
        "B2": b2,
        "limitations": [
            "throughput measures the local UE-tunnel-to-Ubuntu-host path, not external internet capacity",
            "B2 is skipped because the current snapshot lacks event-rate and before/after telemetry",
            "Sequential measurements are not a randomized controlled comparison",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()