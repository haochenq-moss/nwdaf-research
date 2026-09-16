#!/usr/bin/env python3
"""Create a deterministic whole-run split for supplemental campaign data."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/supplemental_large_raw"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train", type=float, default=0.7)
    parser.add_argument("--val", type=float, default=0.15)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if args.train + args.val >= 1:
        raise SystemExit("train + val must be less than 1")
    assignments: dict[str, str] = {}
    for scenario_dir in sorted({
        json.loads(path.read_text(encoding="utf-8")).get("scenario_id")
        for path in args.root.glob("R*/metadata.json")
    }):
        run_ids = []
        for path in sorted(args.root.glob("R*/metadata.json")):
            if json.loads(path.read_text(encoding="utf-8")).get("scenario_id") == scenario_dir:
                run_ids.append(path.parent.name)
        random.Random(f"{args.seed}:{scenario_dir}").shuffle(run_ids)
        train_count = int(len(run_ids) * args.train)
        val_count = int(len(run_ids) * args.val)
        for run_id in run_ids[:train_count]:
            assignments[run_id] = "train"
        for run_id in run_ids[train_count:train_count + val_count]:
            assignments[run_id] = "val"
        for run_id in run_ids[train_count + val_count:]:
            assignments[run_id] = "test"
    output = args.output or args.root / "_split_manifest.json"
    counts = {split: sum(value == split for value in assignments.values()) for split in ("train", "val", "test")}
    report = {"seed": args.seed, "policy": "whole-run scenario-stratified", "assignments": assignments, "counts": counts}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()