#!/usr/bin/env python3
"""Exploratory evaluation of real SBI/PFCP features on supplemental runs.

This is a small supplemental campaign, not a replacement for the frozen pilot
test split. Entire runs are held out by scenario: two runs train and one run
tests for each scenario.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

from nwdaf_research.preprocessing.features import RunFeatureBuilder


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/supplemental_raw"))
    parser.add_argument("--split-manifest", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path("evaluation/supplemental_network_model.json"))
    args = parser.parse_args()
    split_manifest_path = args.split_manifest or args.root / "_split_manifest.json"
    split_manifest = json.loads(split_manifest_path.read_text(encoding="utf-8"))
    builder = RunFeatureBuilder(args.root)
    rows = []
    for run_dir in sorted(builder.raw_root.glob("R*")):
        if not run_dir.is_dir():
            continue
        features = builder.build_features_for_run(run_dir.name)
        rows.append({"run_id": run_dir.name, "scenario": features["scenario_id"], "label": int(features["ground_truth_anomalous"]), "features": features})

    train = [row for row in rows if split_manifest["assignments"].get(row["run_id"]) == "train"]
    test = [row for row in rows if split_manifest["assignments"].get(row["run_id"]) == "test"]

    groups = {
        "network_only": [
            "sbi_event_count", "sbi_error_event_count", "pfcp_event_count",
            "pfcp_request_count", "pfcp_response_count",
        ],
        "combined": [
            "linux_event_count", "process_event_count", "linux_load_1m_mean",
            "linux_load_1m_std", "memory_available_ratio_mean", "sbi_event_count",
            "sbi_error_event_count", "pfcp_event_count", "pfcp_request_count",
            "pfcp_response_count",
        ],
    }
    results = {
        "split_manifest": str(split_manifest_path),
        "split_policy": split_manifest.get("policy"),
        "train_runs": [row["run_id"] for row in train],
        "test_runs": [row["run_id"] for row in test],
        "groups": {},
    }
    for name, feature_names in groups.items():
        x_train = np.array([[float(row["features"].get(key, 0.0)) for key in feature_names] for row in train])
        x_test = np.array([[float(row["features"].get(key, 0.0)) for key in feature_names] for row in test])
        y_train = [row["label"] for row in train]
        y_test = [row["label"] for row in test]
        model = RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")
        model.fit(x_train, y_train)
        predictions = model.predict(x_test).tolist()
        results["groups"][name] = {
            "features": feature_names,
            "classification_report": classification_report(y_test, predictions, output_dict=True, zero_division=0),
            "confusion_matrix": confusion_matrix(y_test, predictions, labels=[0, 1]).tolist(),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()