#!/usr/bin/env python3
"""Materialize input-test snapshots into NWDAF run directories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.input_testing.snapshot_runs import materialize_input_test_runs


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run_dirs = materialize_input_test_runs(args.campaign_dir)
    except (FileNotFoundError, FileExistsError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({
        "materialized_runs": [str(path) for path in run_dirs],
        "network_event_streams_fabricated": False,
    }, indent=2))


if __name__ == "__main__":
    main()