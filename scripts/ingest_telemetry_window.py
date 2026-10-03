#!/usr/bin/env python3
"""Validate a heartbeat-bearing JSONL window; optional inference never authorizes response."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer
from nwdaf_research.live.telemetry_window import CONTRACT_SOURCES, FULL_CONTRACT, CollectorHealth, TelemetryWindow, parse_time


def ingest_records(path: Path, window: TelemetryWindow) -> None:
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if row["type"] == "seal":
                    if window.is_sealed():
                        raise ValueError("duplicate seal marker")
                    window.seal(row["observed_at"])
                elif row["type"] == "snapshot":
                    health = {
                        source: CollectorHealth(
                            parse_time(value["heartbeat_at"]), value["collector_healthy"],
                            value["telemetry_source_synced"], parse_time(value["observed_through"]),
                        )
                        for source, value in row["collectors"].items()
                    }
                    window.add_snapshot(
                        row["observed_at"], counters=row["counters"],
                        linux_sample=row["linux_sample"], collectors=health,
                    )
                else:
                    raise ValueError("unsupported record type")
                window.inspect(row["observed_at"])
            except (KeyError, TypeError, ValueError, AttributeError) as error:
                raise ValueError(f"Invalid telemetry record at line {number}: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path, required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--duration-sec", type=float, default=10.0)
    parser.add_argument("--heartbeat-timeout-sec", type=float, default=2.0)
    parser.add_argument("--minimum-linux-events", type=int, default=2)
    parser.add_argument("--contract", choices=tuple(CONTRACT_SOURCES), default=FULL_CONTRACT)
    parser.add_argument("--score", action="store_true", help="Score only structurally ready windows")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    args = parser.parse_args(argv)
    try:
        window = TelemetryWindow(
            args.window_start, duration_sec=args.duration_sec,
            heartbeat_timeout_sec=args.heartbeat_timeout_sec,
            minimum_linux_events=args.minimum_linux_events,
            contract=args.contract,
        )
        ingest_records(args.snapshots, window)
        report = window.inspect(args.as_of)
        if args.score:
            report = NWDAFResearchAnalyzer(args.raw_root).score_live_window(window, now=args.as_of)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "READY" or report.get("inference_performed") else 1


if __name__ == "__main__":
    raise SystemExit(main())