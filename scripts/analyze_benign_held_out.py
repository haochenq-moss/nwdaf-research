#!/usr/bin/env python3
"""Unblind only the hash-bound descriptive analysis, without fitting or scoring a model."""

import argparse
import json
from pathlib import Path

from nwdaf_research.live.descriptive_analysis import analyze_held_out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--analysis-lock", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite an existing result")
    try:
        report = analyze_held_out(args.root, lock_path=args.analysis_lock, authorization_path=args.authorization)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({key: report[key] for key in (
        "planned_pair_count", "verified_pair_count", "invalid_pair_count", "primary_endpoint_summary", "interpretation",
    )}, indent=2))


if __name__ == "__main__":
    main()