#!/usr/bin/env python3
"""Show one read-only progress snapshot for a supplemental campaign."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/supplemental_large_raw"))
    parser.add_argument("--expected", type=int, default=120)
    args = parser.parse_args()

    run_dirs = sorted(path for path in args.root.glob("R*") if path.is_dir())
    completed = 0
    failed = 0
    scenarios: Counter[str] = Counter()
    sbi_events = 0
    pfcp_events = 0
    for run_dir in run_dirs:
        metadata_path = run_dir / "metadata.json"
        ground_truth_path = run_dir / "ground_truth.json"
        if metadata_path.exists() and ground_truth_path.exists():
            completed += 1
            ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
            scenarios[str(ground_truth.get("scenario_id", "unknown"))] += 1
        else:
            failed += 1
        for path, counter in (
            (run_dir / "sbi" / "events.jsonl", "sbi"),
            (run_dir / "pfcp" / "events.jsonl", "pfcp"),
        ):
            if path.exists():
                count = sum(1 for line in path.open(encoding="utf-8", errors="replace") if line.strip())
                if counter == "sbi":
                    sbi_events += count
                else:
                    pfcp_events += count

    percent = min(100.0, completed * 100.0 / args.expected) if args.expected else 0.0
    width = 40
    filled = int(width * percent / 100.0)
    bar = "#" * filled + "." * (width - filled)
    print(f"[{bar}] {completed}/{args.expected} ({percent:.1f}%)")
    print(f"completed={completed} incomplete_or_failed={failed} scenarios={dict(sorted(scenarios.items()))}")
    print(f"sbi_events={sbi_events} pfcp_events={pfcp_events}")


if __name__ == "__main__":
    main()
