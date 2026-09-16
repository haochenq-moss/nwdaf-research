#!/usr/bin/env python3
"""Measure the B0 live baseline over the real Ubuntu UE tunnel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.live.benchmark import SSHBaselineBenchmark


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2222)
    parser.add_argument("--user", default="haochenqin-moss")
    parser.add_argument("--identity-file", default="~/.ssh/id_ecdsa")
    parser.add_argument("--target", default="8.8.8.8")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("evaluation/b0_live.json"))
    args = parser.parse_args()
    measurement = SSHBaselineBenchmark(
        host=args.host, port=args.port, user=args.user, identity_file=args.identity_file
    ).measure(target=args.target, count=args.count)
    report = {"configuration": "B0", "measurement": measurement.as_dict()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()