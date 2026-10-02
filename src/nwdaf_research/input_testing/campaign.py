from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nwdaf_research.input_testing.evaluation import (
    FEATURE_NAMES,
    compare_input_outcomes,
    evaluate_run_detection,
    features_for_runs,
)
from nwdaf_research.input_testing.records import (
    InputCase,
    RunLabel,
    TestOutcome,
    read_jsonl,
    validate_campaign,
)
from nwdaf_research.preprocessing.features import RunFeatureBuilder


def evaluate_campaign(
    campaign_dir: str | Path,
    *,
    runs_root: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate and evaluate one isolated input-testing campaign."""
    campaign_path = Path(campaign_dir)
    cases = read_jsonl(campaign_path / "input_cases.jsonl", InputCase)
    outcomes = read_jsonl(campaign_path / "outcomes.jsonl", TestOutcome)
    labels = read_jsonl(campaign_path / "run_labels.jsonl", RunLabel)
    empty_manifests = [
        filename
        for filename, records in (
            ("input_cases.jsonl", cases),
            ("outcomes.jsonl", outcomes),
            ("run_labels.jsonl", labels),
        )
        if not records
    ]
    if empty_manifests:
        raise ValueError(
            "Campaign manifests are empty: " + ", ".join(empty_manifests)
            + ". Add records from completed, authorized tests; do not use placeholders."
        )
    validate_campaign(cases, outcomes, labels)

    label_counts = {
        split: {
            label: sum(1 for row in labels if row.split == split and row.label == label)
            for label in ("normal", "input_test")
        }
        for split in ("train", "held_out")
    }
    incomplete_splits = [
        split for split, counts in label_counts.items()
        if not counts["normal"] or not counts["input_test"]
    ]
    if incomplete_splits:
        raise ValueError(
            "Need normal and input_test runs in both train and held_out splits; "
            f"current counts: {json.dumps(label_counts, sort_keys=True)}"
        )

    telemetry_root = Path(runs_root) if runs_root is not None else campaign_path / "runs"
    run_ids = sorted(label.run_id for label in labels)
    missing_run_dirs = [run_id for run_id in run_ids if not (telemetry_root / run_id).is_dir()]
    if missing_run_dirs:
        raise ValueError(
            f"Missing NWDAF run directories under {telemetry_root}: "
            + ", ".join(missing_run_dirs)
        )
    feature_rows = features_for_runs(RunFeatureBuilder(telemetry_root), run_ids)
    run_evaluation = evaluate_run_detection(feature_rows, labels)
    linux_features = (
        "linux_event_count",
        "linux_load_1m_mean",
        "linux_load_1m_std",
        "linux_load_1m_max",
        "linux_memory_available_mean",
        "memory_available_ratio_mean",
    )
    no_duration_features = tuple(name for name in FEATURE_NAMES if name != "duration_sec")
    sensitivity = {
        "all_features": run_evaluation["metrics"],
        "without_duration": evaluate_run_detection(
            feature_rows, labels, feature_names=no_duration_features
        )["metrics"],
        "linux_only": evaluate_run_detection(
            feature_rows, labels, feature_names=linux_features
        )["metrics"],
        "interpretation": (
            "These are small-pilot sensitivity checks, not independent efficacy evidence. "
            "Perfect Linux-only separation alongside short normal windows and variable input-test "
            "windows indicates collection-procedure signatures (sample counts/windowing) may "
            "dominate. SBI request events also directly expose test activity. Match durations, "
            "background SBI activity, and collector cadence before claiming anomaly detection."
        ),
    }

    report: dict[str, Any] = {
        "campaign_id": campaign_path.name,
        "components": sorted({case.component for case in cases}),
        "free5gc_commits": sorted({case.free5gc_commit for case in cases}),
        "run_label_counts": label_counts,
        "input_outcome_comparison": compare_input_outcomes(cases, outcomes),
        "run_detection_evaluation": run_evaluation,
        "feature_sensitivity": sensitivity,
        "interpretation": (
            "Exploratory held-out separation of normal and input-test runs; "
            "not vulnerability classification. Crashes are observations requiring investigation."
        ),
    }

    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report