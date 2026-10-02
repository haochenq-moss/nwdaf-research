#!/usr/bin/env python3
"""Run validated, unexecuted LLM-selected NRF discovery GET candidates."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from nwdaf_research.input_testing.nrf_discovery import (
    run_nrf_discovery_case,
    validate_candidate_path,
)


def _read_candidates(path: Path) -> list[dict[str, object]]:
    rows = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid candidate JSON at line {line_number}") from error
            if row.get("input_source") != "llm_suggested" or row.get("method") != "GET":
                raise ValueError(f"candidate at line {line_number} is not a read-only LLM GET")
            if row.get("execution_status") != "not_run":
                continue
            row["path"] = validate_candidate_path(str(row.get("path", "")))
            rows.append(row)
    return rows


def _next_run_number(campaign_dir: Path) -> int:
    used = []
    labels_path = campaign_dir / "run_labels.jsonl"
    if labels_path.exists():
        for line in labels_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            run_id = json.loads(line).get("run_id", "")
            match = re.fullmatch(r"RLLM(\d{3,})", run_id)
            if match:
                used.append(int(match.group(1)))
    run_root = campaign_dir / "runs"
    if run_root.exists():
        for path in run_root.glob("RLLM*"):
            match = re.fullmatch(r"RLLM(\d{3,})", path.name)
            if match:
                used.append(int(match.group(1)))
    return max(used, default=0) + 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--nf-instance-id", required=True)
    parser.add_argument("--candidate-id", help="run one candidate; default runs all unexecuted candidates sequentially")
    parser.add_argument("--max-candidates", type=int, default=8)
    args = parser.parse_args(argv)
    if args.max_candidates < 1:
        parser.error("--max-candidates must be positive")

    candidate_file = args.campaign_dir / "llm_candidates.jsonl"
    try:
        candidates = _read_candidates(candidate_file)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if args.candidate_id:
        candidates = [row for row in candidates if row.get("candidate_id") == args.candidate_id]
    candidates = candidates[:args.max_candidates]
    if not candidates:
        parser.error("no matching unexecuted, validated candidates found")

    all_rows = [json.loads(line) for line in candidate_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows_by_id = {str(row["candidate_id"]): row for row in all_rows}
    run_number = _next_run_number(args.campaign_dir)
    results = []
    for row in candidates:
        candidate_id = str(row["candidate_id"])
        run_id = f"RLLM{run_number:03d}"
        run_number += 1
        try:
            result = run_nrf_discovery_case(
                campaign_dir=args.campaign_dir,
                run_id=run_id,
                input_id=candidate_id,
                nf_instance_id=args.nf_instance_id,
                request_path=str(row["path"]),
                input_source="llm_suggested",
                generator_model=str(row["model"]),
                trial_group=str(row.get("trial_group") or f"{row['model']}-template-{row.get('template_choice', 'unknown')}"),
                replicate_index=int(row.get("replicate_index", 1)),
                template_choice=int(row["template_choice"]) if row.get("template_choice") is not None else None,
            )
        except (OSError, RuntimeError, ValueError) as error:
            parser.error(f"{candidate_id} stopped: {error}")
        rows_by_id[candidate_id].update({
            "execution_status": "executed",
            "run_id": run_id,
            "http_status": result["http_status"],
            "outcome": result["outcome"],
            "duration_ms": result["duration_ms"],
            "request_sha256": result["request_sha256"],
            "token_persisted": False,
        })
        results.append(result)
        candidate_file.write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in all_rows),
            encoding="utf-8",
        )

    print(json.dumps({"executed_count": len(results), "results": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()