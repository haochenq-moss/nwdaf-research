#!/usr/bin/env python3
"""Revalidate passive campaign artifacts and report feature variation without inference."""

import argparse
import json
from pathlib import Path

from nwdaf_research.live.baseline_evidence import summarize_baseline_campaigns


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-dir", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = summarize_baseline_campaigns(args.campaign_dir)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2, sort_keys=True)
                stream.write("\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()