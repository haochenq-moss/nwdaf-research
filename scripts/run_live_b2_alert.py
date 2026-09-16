#!/usr/bin/env python3
"""Run a real B2 alert-only trial with before/after measurements.

This deliberately uses alert_operator, not tc rate limiting. It validates the
live response path and timing while leaving the UE session and network intact.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path

from nwdaf_research.adapters.http_nf import HTTPNFAdapter
from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer
from nwdaf_research.live.benchmark import SSHBaselineBenchmark
from nwdaf_research.live.ssh_observer import SSHLiveObserver
from nwdaf_research.policy.engine import PolicyEngine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2222)
    parser.add_argument("--user", default="haochenqin-moss")
    parser.add_argument("--identity-file", default="~/.ssh/id_ecdsa")
    parser.add_argument("--agent-endpoint", default="http://127.0.0.1:9090")
    parser.add_argument("--target", default="10.60.0.1")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("evaluation/b2_alert_trial.json"))
    args = parser.parse_args()

    api_key = os.environ.get("RESPONSE_AGENT_API_KEY")
    if not api_key:
        raise SystemExit("Set RESPONSE_AGENT_API_KEY in this terminal before running the B2 trial")
    observer = SSHLiveObserver(
        host=args.host, port=args.port, user=args.user, identity_file=args.identity_file
    )
    benchmark = SSHBaselineBenchmark(
        host=args.host, port=args.port, user=args.user, identity_file=args.identity_file
    )
    analyzer = NWDAFResearchAnalyzer(args.raw_root, model_artifact="models/rf-v1")
    policy = PolicyEngine()
    adapter = HTTPNFAdapter(args.agent_endpoint, api_key)

    before_measurement = benchmark.measure(target=args.target, count=args.count).as_dict()
    before_observation = observer.observe()
    detection_started = time.perf_counter()
    detection = analyzer.score_features(before_observation.features)
    detection_latency_ms = (time.perf_counter() - detection_started) * 1000
    decision_id = f"b2-alert-{uuid.uuid4().hex[:12]}"
    decision = policy.evaluate(
        decision_id=decision_id,
        target_nf="SMF",
        target={"supi": "live-test-observation"},
        action="alert_operator",
        duration=None,
        reason="live_b2_alert_trial",
        confidence=float(detection["confidence"]),
    )
    if not decision.allowed:
        raise SystemExit(f"Policy rejected alert trial: {decision.rejection_reason}")
    response_started = time.perf_counter()
    response = adapter.execute(decision)
    mitigation_latency_ms = (time.perf_counter() - response_started) * 1000
    after_measurement = benchmark.measure(target=args.target, count=args.count).as_dict()
    after_observation = observer.observe()
    report = {
        "configuration": "B2",
        "action": "alert_operator",
        "decision_id": decision_id,
        "detection": detection,
        "detection_latency_ms": detection_latency_ms,
        "response": response,
        "mitigation_latency_ms": mitigation_latency_ms,
        "before": {"observation": before_observation.evidence, "network": before_measurement},
        "after": {"observation": after_observation.evidence, "network": after_measurement},
        "verification": {
            "status": "measured",
            "network_effect_expected": False,
            "recovery_time": "not_applicable_for_alert_operator",
            "throughput_change": "not_attributable_to_alert_operator",
            "packet_loss_change": after_measurement["packet_loss_percent"]
            - before_measurement["packet_loss_percent"]
            if before_measurement["packet_loss_percent"] is not None
            and after_measurement["packet_loss_percent"] is not None
            else "unavailable",
            "rtt_change_ms": after_measurement["rtt_mean_ms"] - before_measurement["rtt_mean_ms"]
            if before_measurement["rtt_mean_ms"] is not None
            and after_measurement["rtt_mean_ms"] is not None
            else "unavailable",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()