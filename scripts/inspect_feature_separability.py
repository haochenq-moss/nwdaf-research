#!/usr/bin/env python3
"""Diagnostic-only univariate feature separability check for a fresh campaign.

This is exploratory analysis, not a frozen detector evaluation: it uses all
runs (dev + held_out combined) to get maximum statistical power for asking
"does any single feature carry a usable signal at all?" It must not be used
to select features or thresholds for the dev/held_out B0/B1 comparison in
evaluate_e1_e3.py; that comparison remains the frozen result.

For each numeric feature, reports:
- per-class mean/std
- single-feature ROC AUC (feature value as the positive-class score)
- ROC AUC computed with the feature sign flipped, so "informative but inverted"
  features are visible too (report max(auc, 1-auc) as an inversion-corrected
  discriminative Auc, but always show the raw and flipped auc explicitly)
"""
import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

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
    rows = []
    for run_id in loader.discover_runs():
        run = loader.load_run(run_id)
        row = builder.build_features_for_run(run_id)
        features = {
            key: numeric_value(value)
            for key, value in row.items()
            if key not in EXCLUDED_KEYS and numeric_value(value) is not None
        }
        rows.append({
            "run_id": run_id,
            "label": int(bool(run["ground_truth"]["anomalous"])),
            "security_label": int(bool(run["ground_truth"]["security"])),
            "features": features,
        })
    return rows


def analyze(rows, label_key, feature_names):
    labels = np.array([row["label"] if label_key == "label" else row["security_label"] for row in rows])
    if len(set(labels.tolist())) < 2:
        return {}
    results = {}
    for name in feature_names:
        values = np.array([row["features"].get(name, 0.0) for row in rows])
        if np.all(values == values[0]):
            results[name] = {"constant": True}
            continue
        try:
            auc = float(roc_auc_score(labels, values))
        except ValueError:
            continue
        results[name] = {
            "auc": auc,
            "auc_inversion_corrected": max(auc, 1 - auc),
            "mean_positive": float(values[labels == 1].mean()) if (labels == 1).any() else None,
            "mean_negative": float(values[labels == 0].mean()) if (labels == 0).any() else None,
            "std_positive": float(values[labels == 1].std()) if (labels == 1).any() else None,
            "std_negative": float(values[labels == 0].std()) if (labels == 0).any() else None,
        }
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", default="campaign_20260925_e1e3_v2")
    parser.add_argument("--raw-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()

    raw_root = args.raw_root or (REPO_ROOT / "data" / "raw" / args.campaign_id)
    output_path = args.output or (
        REPO_ROOT / "data" / "processed" / "{}_feature_separability.json".format(args.campaign_id)
    )

    rows = build_rows(raw_root)
    feature_names = sorted({key for row in rows for key in row["features"]})

    anomalous_results = analyze(rows, "label", feature_names)
    security_results = analyze(rows, "security_label", feature_names)

    def top_by_auc(results):
        scored = [
            (name, info["auc_inversion_corrected"])
            for name, info in results.items()
            if "auc_inversion_corrected" in info
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[: args.top]

    output = {
        "campaign_id": args.campaign_id,
        "run_count": len(rows),
        "caveat": (
            "Diagnostic only: uses all runs (dev+held_out combined) for maximum "
            "statistical power to check for any usable univariate signal. Not a "
            "frozen evaluation and must not be used to select features/thresholds "
            "for the dev/held_out B0/B1 comparison in evaluate_e1_e3.py."
        ),
        "anomalous_label": {
            "per_feature": anomalous_results,
            "top_by_discriminative_auc": top_by_auc(anomalous_results),
        },
        "security_label": {
            "per_feature": security_results,
            "top_by_discriminative_auc": top_by_auc(security_results),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output_path),
        "run_count": len(rows),
        "top_features_anomalous_label": output["anomalous_label"]["top_by_discriminative_auc"],
        "top_features_security_label": output["security_label"]["top_by_discriminative_auc"],
    }, indent=2))


if __name__ == "__main__":
    main()
