#!/usr/bin/env python3
"""Train the validated baseline and write a reproducible model artifact."""

from __future__ import annotations

import argparse
from pathlib import Path

from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("models/rf-v1"))
    args = parser.parse_args()
    manifest = NWDAFResearchAnalyzer(args.raw_root).save_model_artifact(args.output)
    print(manifest)


if __name__ == "__main__":
    main()