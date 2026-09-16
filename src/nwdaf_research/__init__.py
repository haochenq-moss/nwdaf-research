"""NWDAF research package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analytics.nwdaf import NWDAFResearchAnalyzer
from .ingestion.loader import DatasetLoader

__all__ = ["DatasetLoader", "NWDAFResearchAnalyzer"]


def _resolve_raw_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "data" / "raw").exists():
        return cwd / "data" / "raw"
    package_root = Path(__file__).resolve().parents[2]
    if (package_root / "data" / "raw").exists():
        return package_root / "data" / "raw"
    raise FileNotFoundError("Dataset root not found. Expected data/raw under the current project directory.")


def main() -> None:
    parser = argparse.ArgumentParser(description="NWDAF research analytics CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    score_parser = subparsers.add_parser("score", help="Score a single run")
    score_parser.add_argument("--run-id", required=True, help="Run identifier, e.g. R00001")

    batch_parser = subparsers.add_parser("batch", help="Score every run and export JSON")
    batch_parser.add_argument("--output", default="evaluation/run_scores.json", help="Path to the JSON export")

    evaluate_parser = subparsers.add_parser("evaluate", help="Print the validated anomaly baseline metrics")

    args = parser.parse_args()
    raw_root = _resolve_raw_root()
    analyzer = NWDAFResearchAnalyzer(raw_root)

    if args.command == "score":
        result = analyzer.score_run(args.run_id)
        print(json.dumps(result, indent=2))
        return

    if args.command == "batch":
        results = analyzer.export_batch_scores(args.output)
        print(json.dumps({"count": len(results), "output": args.output}, indent=2))
        return

    if args.command == "evaluate":
        print(json.dumps(analyzer.evaluate(), indent=2))
        return

    parser.error(f"Unsupported command: {args.command}")
