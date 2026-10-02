#!/usr/bin/env python3
"""Import exact seed inputs from a free5GC security-lab AFL matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.input_testing.fuzz_import import import_afl_matrix_campaign


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-campaign", type=Path, required=True, help="security-lab AFL campaign directory")
    parser.add_argument("--campaign-dir", type=Path, required=True, help="new NWDAF input-testing campaign directory")
    args = parser.parse_args()
    try:
        report = import_afl_matrix_campaign(args.source_campaign, args.campaign_dir)
    except (FileNotFoundError, FileExistsError, ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({
        "campaign_id": args.campaign_dir.name,
        "input_case_count": report["input_case_count"],
        "network_replay": report["network_replay"],
        "telemetry": report["telemetry"],
    }, indent=2))


if __name__ == "__main__":
    main()