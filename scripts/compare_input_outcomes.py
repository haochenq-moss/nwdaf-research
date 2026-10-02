#!/usr/bin/env python3
"""Summarize completed ordinary and LLM-suggested input outcomes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.input_testing.evaluation import compare_input_outcomes
from nwdaf_research.input_testing.records import InputCase, TestOutcome, read_jsonl


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        cases = read_jsonl(args.campaign_dir / "input_cases.jsonl", InputCase)
        outcomes = read_jsonl(args.campaign_dir / "outcomes.jsonl", TestOutcome)
        summary = compare_input_outcomes(cases, outcomes)
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))

    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()