#!/usr/bin/env python3
"""Read-only structural preflight for a Fuzz-to-NWDAF campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.input_testing.readiness import inspect_campaign_readiness


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, help="Defaults to <campaign-dir>/runs")
    args = parser.parse_args(argv)
    report = inspect_campaign_readiness(args.campaign_dir, runs_root=args.runs_root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["structurally_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())