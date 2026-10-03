from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from nwdaf_research.input_testing.records import (
    InputCase, RunLabel, TestOutcome, read_jsonl, validate_campaign,
)


def inspect_campaign_readiness(
    campaign_dir: str | Path, *, runs_root: str | Path | None = None,
) -> dict[str, Any]:
    """Inspect offline evidence without writing files or authorizing live actions."""
    campaign = Path(campaign_dir).resolve()
    telemetry = Path(runs_root).resolve() if runs_root is not None else campaign / "runs"
    blockers: list[str] = []
    warnings: list[str] = []

    def load(filename: str, record_type: Any) -> Any:
        try:
            rows = read_jsonl(campaign / filename, record_type)
            if not rows:
                blockers.append(f"Empty manifest: {filename}")
            return rows
        except (OSError, ValueError) as error:
            blockers.append(f"Cannot read {filename}: {error}")
            return []

    cases: list[InputCase] = load("input_cases.jsonl", InputCase)
    outcomes: list[TestOutcome] = load("outcomes.jsonl", TestOutcome)
    labels: list[RunLabel] = load("run_labels.jsonl", RunLabel)
    try:
        validate_campaign(cases, outcomes, labels)
    except ValueError as error:
        blockers.append(str(error))
    for case in cases:
        corpus = (campaign / case.corpus_path).resolve()
        if not corpus.is_relative_to(campaign):
            blockers.append(f"Corpus escapes campaign: {case.input_id}")
            continue
        try:
            if hashlib.sha256(corpus.read_bytes()).hexdigest() != case.input_sha256:
                blockers.append(f"Corpus SHA-256 mismatch: {case.input_id}")
        except OSError as error:
            blockers.append(f"Cannot read corpus for {case.input_id}: {error}")

    counts = {
        split: {label: sum(row.split == split and row.label == label for row in labels)
                for label in ("normal", "input_test")}
        for split in ("train", "held_out")
    }
    for split, split_counts in counts.items():
        if not all(split_counts.values()):
            blockers.append(f"Need normal and input_test runs in {split}")
    case_by_id = {case.input_id: case for case in cases}
    split_by_run = {label.run_id: label.split for label in labels}
    partitions: dict[tuple[str, str], set[str]] = {}
    observed_runs = {outcome.run_id for outcome in outcomes}
    for label in labels:
        if label.label == "input_test" and label.run_id not in observed_runs:
            blockers.append(f"Input-test run has no outcome: {label.run_id}")
    for outcome in outcomes:
        case = case_by_id.get(outcome.input_id)
        split = split_by_run.get(outcome.run_id)
        if case is None or split is None:
            continue
        identities = [("input_sha256", case.input_sha256)]
        if case.trial_group:
            identities.append(("trial_group", case.trial_group))
        for identity in identities:
            partitions.setdefault(identity, set()).add(split)
    for (kind, value), splits in sorted(partitions.items()):
        if len(splits) > 1:
            blockers.append(f"Cross-split leakage for {kind}: {value}")

    source_counts: dict[str, dict[str, int | None]] = {}
    for label in labels:
        run = (telemetry / label.run_id).resolve()
        if not run.is_relative_to(telemetry) or run == telemetry:
            blockers.append(f"Unsafe run_id: {label.run_id}")
            continue
        for filename in ("metadata.json", "ground_truth.json", "timeline.json"):
            try:
                value = json.loads((run / filename).read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("expected a JSON object")
            except (OSError, ValueError) as error:
                blockers.append(f"Invalid run artifact {label.run_id}/{filename}: {error}")
        source_counts[label.run_id] = {}
        for source in ("linux", "sbi", "pfcp", "free5gc"):
            path = run / source / "events.jsonl"
            count = None
            if path.is_file():
                try:
                    count = 0
                    with path.open(encoding="utf-8") as stream:
                        for line in stream:
                            if line.strip():
                                if not isinstance(json.loads(line), dict):
                                    raise ValueError("expected JSON event objects")
                                count += 1
                except (OSError, ValueError) as error:
                    blockers.append(f"Invalid telemetry {label.run_id}/{source}: {error}")
                    count = None
            source_counts[label.run_id][source] = count
            if source == "linux" and not count:
                blockers.append(f"Missing observed Linux samples: {label.run_id}")
            elif source != "linux" and count is None:
                warnings.append(f"Telemetry stream absent: {label.run_id}/{source}")
    warnings.append("Empty network streams do not prove collector availability; inspect capture evidence.")
    return {
        "schema_version": "fuzz-to-nwdaf-readiness-v1",
        "campaign_id": campaign.name,
        "structurally_ready": not blockers,
        "input_case_count": len(cases),
        "outcome_count": len(outcomes),
        "run_label_counts": counts,
        "source_event_counts": source_counts,
        "blockers": blockers,
        "warnings": warnings,
        "interpretation": (
            "Structural preflight only, not replay/response authorization, evidence authenticity, "
            "fixture/cleanup verification, statistical sufficiency, or a vulnerability finding. "
            "Match collection windows and cadence and review telemetry availability before evaluation."
        ),
    }