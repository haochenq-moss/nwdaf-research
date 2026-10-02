#!/usr/bin/env python3
"""Capture passive no-request free5GC baseline runs for train/held-out evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.input_testing.normal_baseline import capture_normal_baseline


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--train-count", type=int, default=2)
    parser.add_argument("--held-out-count", type=int, default=2)
    parser.add_argument("--duration-sec", type=float, default=2.0)
    args = parser.parse_args(argv)
    if args.train_count < 1 or args.held_out_count < 1:
        parser.error("train and held-out counts must both be at least one")

    results = []
    try:
        for split, count in (("train", args.train_count), ("held_out", args.held_out_count)):
            for _ in range(count):
                results.append(capture_normal_baseline(
                    campaign_dir=args.campaign_dir,
                    split=split,
                    duration_sec=args.duration_sec,
                ))
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({"normal_run_count": len(results), "runs": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()