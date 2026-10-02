#!/usr/bin/env python3
"""Split input-test runs by unique input hash without train/held-out leakage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.input_testing.splits import assign_input_test_splits


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    try:
        result = assign_input_test_splits(args.campaign_dir, seed=args.seed)
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()