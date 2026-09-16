#!/usr/bin/env python3
"""Run randomized B0/B1 live probes to reduce sequential order bias."""

from __future__ import annotations

import argparse
import json
import random
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
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("evaluation/randomized_live.json"))
    args = parser.parse_args()
    order = ["B0", "B1"]
    random.Random(args.seed).shuffle(order)
    benchmark = SSHBaselineBenchmark(host=args.host, port=args.port, user=args.user, identity_file=args.identity_file)
    observer = SSHLiveObserver(host=args.host, port=args.port, user=args.user, identity_file=args.identity_file)
    analyzer = NWDAFResearchAnalyzer(args.raw_root, model_artifact="models/rf-v1")
    results = {"seed": args.seed, "order": order, "measurements": {}}
    for configuration in order:
        network = benchmark.measure(target=args.target, count=5).as_dict()
        entry = {"network": network}
        if configuration == "B1":
            observation = observer.observe()
            started = time.perf_counter()
            entry["analytics"] = analyzer.score_features(observation.features)
            entry["detection_latency_ms"] = (time.perf_counter() - started) * 1000
        results["measurements"][configuration] = entry
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()