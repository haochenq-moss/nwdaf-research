#!/usr/bin/env python3
"""Run and record one fixed, read-only, OAuth-authenticated NRF discovery case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.input_testing.nrf_discovery import run_nrf_discovery_case


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--input-id", required=True)
    parser.add_argument(
        "--nf-instance-id",
        required=True,
        help="registered AMF NF instance UUID whose certificate is installed at the NRF",
    )
    args = parser.parse_args(argv)

    try:
        result = run_nrf_discovery_case(
            campaign_dir=args.campaign_dir,
            run_id=args.run_id,
            input_id=args.input_id,
            nf_instance_id=args.nf_instance_id,
        )
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()