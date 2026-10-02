#!/usr/bin/env python3
"""Evaluate one input-testing campaign against campaign-local NWDAF runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.input_testing.campaign import evaluate_campaign


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument(
        "--runs-root",
        type=Path,
        help="NWDAF run directories; defaults to <campaign-dir>/runs",
    )
    parser.add_argument("--output", type=Path, help="defaults to <campaign-dir>/evaluation.json")
    args = parser.parse_args(argv)

    output = args.output or args.campaign_dir / "evaluation.json"
    try:
        report = evaluate_campaign(
            args.campaign_dir,
            runs_root=args.runs_root,
            output_path=output,
        )
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()