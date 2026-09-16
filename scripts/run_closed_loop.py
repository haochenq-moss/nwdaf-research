#!/usr/bin/env python3
"""Run one evidence-backed closed-loop demo using a verified pilot run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.adapters.mock_nf import MockNFAdapter
from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer
from nwdaf_research.loop.controller import ClosedLoopController
from nwdaf_research.policy.engine import PolicyEngine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="R00012")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    analyzer = NWDAFResearchAnalyzer(args.raw_root)
    controller = ClosedLoopController(analyzer, PolicyEngine(), MockNFAdapter())
    event = controller.run(
        run_id=args.run_id,
        decision_id=f"demo-{args.run_id}",
        target_nf="SMF",
        target={"supi": "pilot-run-target"},
        action="rate_limit",
        reason="pilot_run_anomaly",
        observation=analyzer.features_for_run(args.run_id),
        duration=30,
    )
    print(json.dumps(event, indent=2))


if __name__ == "__main__":
    main()