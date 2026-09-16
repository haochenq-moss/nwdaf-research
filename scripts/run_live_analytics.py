#!/usr/bin/env python3
"""Collect one real Ubuntu testbed snapshot and run the trained model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer
from nwdaf_research.live.ssh_observer import SSHLiveObserver


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2222)
    parser.add_argument("--user", default="haochenqin-moss")
    parser.add_argument("--identity-file", default="~/.ssh/id_ecdsa")
    parser.add_argument("--output", type=Path, default=Path("evaluation/live_latest.json"))
    args = parser.parse_args()

    observation = SSHLiveObserver(
        host=args.host,
        port=args.port,
        user=args.user,
        identity_file=args.identity_file,
    ).observe()
    analyzer = NWDAFResearchAnalyzer(args.raw_root)
    result = analyzer.score_features(observation.features)
    report = {
        "observed_at": observation.observed_at,
        "host": observation.host,
        "observation": {
            "features": observation.features,
            "evidence": observation.evidence,
            "unavailable_features": observation.unavailable_features,
            "autonomous_response_eligible": observation.complete_for_autonomous_response,
        },
        "analytics": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()