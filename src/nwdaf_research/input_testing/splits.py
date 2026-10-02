from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from nwdaf_research.input_testing.records import (
    InputCase,
    RunLabel,
    TestOutcome,
    read_jsonl,
    validate_campaign,
    write_jsonl,
)


def assign_input_test_splits(campaign_dir: str | Path, *, seed: int = 42) -> dict[str, Any]:
    """Assign input-test runs by input hash so duplicate bytes never leak across splits."""
    campaign = Path(campaign_dir)
    cases = read_jsonl(campaign / "input_cases.jsonl", InputCase)
    outcomes = read_jsonl(campaign / "outcomes.jsonl", TestOutcome)
    labels_path = campaign / "run_labels.jsonl"
    labels = read_jsonl(labels_path, RunLabel)
    validate_campaign(cases, outcomes, labels)

    case_by_id = {case.input_id: case for case in cases}
    labels_by_run = {label.run_id: label for label in labels}
    runs_by_hash: dict[str, list[str]] = {}
    for outcome in outcomes:
        label = labels_by_run[outcome.run_id]
        if label.label != "input_test":
            continue
        digest = case_by_id[outcome.input_id].input_sha256
        runs_by_hash.setdefault(digest, []).append(outcome.run_id)

    if len(runs_by_hash) < 2:
        raise ValueError("at least two distinct input hashes are required for a leakage-safe split")

    rng = random.Random(seed)
    groups = sorted(runs_by_hash.items(), key=lambda item: (-len(item[1]), item[0]))
    assigned: dict[str, str] = {}
    counts = {"train": 0, "held_out": 0}
    for digest, run_ids in groups:
        if counts["train"] == counts["held_out"]:
            split = rng.choice(("train", "held_out"))
        else:
            split = min(counts, key=counts.get)
        for run_id in run_ids:
            assigned[run_id] = split
        counts[split] += len(run_ids)

    updated = [
        RunLabel(label.run_id, label.label, assigned.get(label.run_id, label.split))
        for label in labels
    ]
    write_jsonl(labels_path, updated)

    hash_partitions: dict[str, set[str]] = {}
    for digest, run_ids in runs_by_hash.items():
        hash_partitions[digest] = {assigned[run_id] for run_id in run_ids}
    if any(len(partitions) != 1 for partitions in hash_partitions.values()):
        raise AssertionError("input hash leaked across train and held_out")

    return {
        "seed": seed,
        "input_test_run_counts": counts,
        "distinct_input_hashes": len(runs_by_hash),
        "run_assignments": dict(sorted(assigned.items())),
    }