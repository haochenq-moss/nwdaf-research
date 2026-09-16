#!/usr/bin/env python3
"""Evaluate B0/B1/B2 without training on the held-out test labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.experiments.configurations import evaluate_configurations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/configurations.json"))
    args = parser.parse_args()
    result = evaluate_configurations(str(args.raw_root))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()