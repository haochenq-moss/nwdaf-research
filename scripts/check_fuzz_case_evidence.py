#!/usr/bin/env python3
"""Check an externally collected fuzz-case evidence chain without sending traffic."""

import argparse
import json
from pathlib import Path

from nwdaf_research.input_testing.protocol_evidence import inspect_case_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = inspect_case_evidence(args.bundle_dir)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["evidence_chain_status"] == "REFERENCES_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())