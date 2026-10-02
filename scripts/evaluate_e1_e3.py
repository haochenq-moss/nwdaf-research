#!/usr/bin/env python3
"""E1 (detection: B0 threshold vs B1 Random Forest) and E3 (held-out
evaluation) for the fresh campaign_20260925_e1e3 dataset.

Design, matching the paper's constraints:
- B0's threshold and B1's classifier are both fit using only the "dev"
  partition (50 runs). Neither is tuned against "held_out" in any way.
- "held_out" (50 runs, disjoint seeds from "dev"; see configs/campaign_e1e3.yaml)
  is evaluated exactly once, using the already-fixed threshold/model.
- This intentionally reuses the existing, tested metric helpers from
  nwdaf_research.experiments.configurations (binary/probability metrics,
  bootstrap F1 CI, per-group breakdown) rather than duplicating them.
- This is a small sample (50/50) single held-out split, not a repeated
  cross-validation study; report it as such, not as a large-scale result.
- E2 (host/5G modality ablation) is not computed here; see TODOS.md.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score

from nwdaf_research.experiments.configurations import (
    _binary_metrics,
    _per_group,
    _probability_metrics,
    _bootstrap_f1_ci,
)
from nwdaf_research.ingestion.loader import DatasetLoader
from nwdaf_research.preprocessing.features import RunFeatureBuilder

REPO_ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_KEYS = {
    "run_id", "ground_truth_class", "ground_truth_anomalous", "ground_truth_scenario_id",
    "ground_truth_security", "ground_truth_severity", "scenario_id", "load_profile",
    "created_at", "host_id", "split", "timeline_keys", "host_event_type_counts",
    "process_event_by_type",
}


def numeric_value(value):
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def build_rows(raw_root):
    loader = DatasetLoader(raw_root)
    builder = RunFeatureBuilder(raw_root)
    rows = {"dev": [], "held_out": []}
    for run_id in loader.discover_runs():
        run = loader.load_run(run_id)
        row = builder.build_features_for_run(run_id)
        split = run["split"]
        if split not in rows:
            continue
        features = {
            key: numeric_value(value)
            for key, value in row.items()
            if key not in EXCLUDED_KEYS and numeric_value(value) is not None
        }
        rows[split].append({
            "run_id": run_id,
            "scenario_id": row.get("scenario_id"),
            "load_profile": row.get("load_profile"),
            "label": int(bool(run["ground_truth"]["anomalous"])),
            "security_label": int(bool(run["ground_truth"]["security"])),
            "features": features,
        })
    return rows


def vectors(rows, names):
    return np.array([[row["features"].get(name, 0.0) for name in names] for row in rows], dtype=float)


def evaluate_label(dev, held_out, feature_names, label_key, description_suffix):
    dev_labels = [row[label_key] for row in dev]
    held_out_labels = [row[label_key] for row in held_out]

    threshold_candidates = sorted({row["features"].get("linux_load_1m_mean", 0.0) for row in dev}) or [0.0]
    threshold = float(max(
        threshold_candidates,
        key=lambda candidate: f1_score(
            dev_labels,
            [int(row["features"].get("linux_load_1m_mean", 0.0) >= candidate) for row in dev],
            zero_division=0,
        ),
    ))
    b0_predictions = [int(row["features"].get("linux_load_1m_mean", 0.0) >= threshold) for row in held_out]

    classifier = RandomForestClassifier(random_state=42, n_estimators=200, class_weight="balanced")
    classifier.fit(vectors(dev, feature_names), dev_labels)
    b1_probabilities = classifier.predict_proba(vectors(held_out, feature_names))[:, 1]
    b1_predictions = [int(probability >= 0.5) for probability in b1_probabilities]

    return {
        "positive_label": label_key,
        "dev_positive_count": sum(dev_labels),
        "held_out_positive_count": sum(held_out_labels),
        "B0": {
            "description": "Linux load threshold baseline (threshold fit on dev only){}".format(description_suffix),
            "threshold_linux_load_1m": threshold,
            "metrics": _binary_metrics(held_out_labels, b0_predictions),
            "per_scenario": _per_group(held_out, b0_predictions, "scenario_id"),
        },
        "B1": {
            "description": "Linux telemetry Random Forest detection (fit on dev only){}".format(description_suffix),
            "metrics": _binary_metrics(held_out_labels, b1_predictions),
            "probability_metrics": _probability_metrics(held_out_labels, b1_probabilities),
            "f1_bootstrap_ci": _bootstrap_f1_ci(held_out_labels, b1_probabilities),
            "per_scenario": _per_group(held_out, b1_predictions, "scenario_id"),
            "feature_importances": dict(
                sorted(
                    zip(feature_names, classifier.feature_importances_.tolist()),
                    key=lambda pair: pair[1],
                    reverse=True,
                )[:10]
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", default="campaign_20260925_e1e3")
    parser.add_argument("--raw-root", type=Path, default=None,
                        help="Defaults to data/raw/<campaign-id>")
    parser.add_argument("--output", type=Path, default=None,
                        help="Defaults to data/processed/<campaign-id>_e1_e3_results.json")
    parser.add_argument("--expected-dev", type=int, default=50)
    parser.add_argument("--expected-held-out", type=int, default=50)
    args = parser.parse_args()

    raw_root = args.raw_root or (REPO_ROOT / "data" / "raw" / args.campaign_id)
    output_path = args.output or (REPO_ROOT / "data" / "processed" / "{}_e1_e3_results.json".format(args.campaign_id))

    rows = build_rows(raw_root)
    dev, held_out = rows["dev"], rows["held_out"]
    if len(dev) != args.expected_dev or len(held_out) != args.expected_held_out:
        raise RuntimeError(
            "Expected exactly {} dev and {} held_out runs, found {} and {}. "
            "Refusing to report results against an unexpected partition size.".format(
                args.expected_dev, args.expected_held_out, len(dev), len(held_out)
            )
        )
    feature_names = sorted({key for row in dev + held_out for key in row["features"]})

    anomalous_results = evaluate_label(dev, held_out, feature_names, "label", "")
    security_results = evaluate_label(
        dev, held_out, feature_names, "security_label",
        " [label=security: true attack (S01/S04/S07/S08/S10) vs normal+benign-hard-negative]",
    )

    results = {
        "campaign_id": args.campaign_id,
        "caveats": [
            "Single 50/50 dev/held_out split, not repeated cross-validation; "
            "treat metrics as a first fresh-campaign estimate, not a large-scale result.",
            "B0 threshold and B1 classifier are both fit using only 'dev'; 'held_out' is "
            "evaluated exactly once and was never used for tuning.",
            "This covers E1 (detection) and E3 (held-out evaluation) only. E2 (host/5G "
            "modality ablation) and E4/E5 (service-level) are not computed here.",
            "'anomalous' (scenario != NORMAL) is severely imbalanced (45/50 positive in "
            "held_out) and both B0 and B1 achieve 0% specificity (every NORMAL run is "
            "misclassified) despite a high F1; see 'security_label_results' for the more "
            "balanced true-attack-vs-rest comparison instead.",
        ],
        "dev_count": len(dev),
        "held_out_count": len(held_out),
        "feature_names": feature_names,
        "configurations": anomalous_results,
        "security_label_results": security_results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output_path),
        "anomalous_label": {
            "B0_f1": anomalous_results["B0"]["metrics"]["f1"],
            "B0_confusion": anomalous_results["B0"]["metrics"]["confusion_matrix"],
            "B1_f1": anomalous_results["B1"]["metrics"]["f1"],
            "B1_confusion": anomalous_results["B1"]["metrics"]["confusion_matrix"],
            "B1_roc_auc": anomalous_results["B1"]["probability_metrics"]["roc_auc"],
        },
        "security_label": {
            "held_out_positive_count": security_results["held_out_positive_count"],
            "B0_f1": security_results["B0"]["metrics"]["f1"],
            "B0_confusion": security_results["B0"]["metrics"]["confusion_matrix"],
            "B1_f1": security_results["B1"]["metrics"]["f1"],
            "B1_confusion": security_results["B1"]["metrics"]["confusion_matrix"],
            "B1_roc_auc": security_results["B1"]["probability_metrics"]["roc_auc"],
        },
    }, indent=2))


if __name__ == "__main__":
    main()
