#!/usr/bin/env python3
"""Generate repeated NRF GET candidates from multiple local Ollama models."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from nwdaf_research.input_testing.trial_generation import (
    DEFAULT_MODELS,
    TEMPLATES,
    build_candidate_rows,
    choose_templates,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--model", action="append", dest="models", help="Ollama model; repeat for multiple models")
    parser.add_argument("--template-count", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--seed", type=int, default=2718)
    args = parser.parse_args(argv)
    models = args.models or list(DEFAULT_MODELS)
    if not 1 <= args.template_count <= len(TEMPLATES) or args.repeats < 1:
        parser.error("template-count must be 1..8 and repeats must be at least 1")

    manifest = args.campaign_dir / "llm_candidates.jsonl"
    try:
        existing = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        candidate_ids = {str(row["candidate_id"]) for row in existing}
        additions = []
        for model_index, model in enumerate(models):
            choices = choose_templates(model, count=args.template_count, seed=args.seed + model_index)
            slug = re.sub(r"[^a-zA-Z0-9]+", "-", model).strip("-").lower()
            batch_indices = [
                int(match.group(1))
                for row in existing
                if row.get("model") == model
                for match in [re.search(r"-b(\d+)-template-", str(row.get("candidate_id", "")))]
                if match
            ]
            legacy_rows = any(row.get("model") == model for row in existing) and not batch_indices
            batch_index = max(batch_indices, default=1 if legacy_rows else 0) + 1
            rows = build_candidate_rows(model, choices, args.repeats, batch_index=batch_index)
            duplicate_ids = candidate_ids.intersection(str(row["candidate_id"]) for row in rows)
            if duplicate_ids:
                raise ValueError(f"candidate IDs already exist: {sorted(duplicate_ids)}")
            candidate_ids.update(str(row["candidate_id"]) for row in rows)
            additions.extend(rows)
        temporary = manifest.with_suffix(manifest.suffix + ".tmp")
        temporary.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in [*existing, *additions]),
            encoding="utf-8",
        )
        temporary.replace(manifest)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as error:
        parser.error(str(error))

    print(json.dumps({
        "added": len(additions),
        "models": models,
        "template_count_per_model": args.template_count,
        "repeats_per_template": args.repeats,
        "execution_status": "not_run",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()