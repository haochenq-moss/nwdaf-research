#!/usr/bin/env python3
"""Build a explicitly incomplete historical feature record without zero-imputing missing data."""

import argparse
import json
from pathlib import Path

from nwdaf_research.input_testing.retrospective_features import build_partial_features


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite existing evidence")
    try:
        report = build_partial_features(args.recovery)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({name: report[name] for name in (
        "run_id", "status", "available_field_count", "missing_field_count", "feature_values", "training_ready",
    )}, indent=2))


if __name__ == "__main__":
    main()