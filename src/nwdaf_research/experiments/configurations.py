from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from nwdaf_research.analytics.baseline import BaselineAnomalyModel


@dataclass(frozen=True)
class ConfigurationEvaluation:
    name: str
    metrics: dict[str, Any]


def _binary_metrics(labels: list[int], predictions: list[int]) -> dict[str, Any]:
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    return {
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "false_positive_rate": float(fp / (fp + tn)) if fp + tn else 0.0,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "test_count": len(labels),
    }


def _rows(model: BaselineAnomalyModel) -> dict[str, list[dict[str, Any]]]:
    rows = {"train": [], "val": [], "test": []}
    for run_id in sorted(model.feature_builder.raw_root.iterdir()):
        if not run_id.is_dir() or not run_id.name.startswith("R"):
            continue
        row = model.feature_builder.build_features_for_run(run_id.name)
        split = model.manifest["assignments"].get(run_id.name)
        if split in rows:
            numeric = {
                key: value
                for key, value in row.items()
                if key
                not in {
                    "run_id",
                    "ground_truth_class",
                    "ground_truth_anomalous",
                    "ground_truth_scenario_id",
                    "ground_truth_security",
                    "ground_truth_severity",
                    "scenario_id",
                    "load_profile",
                    "created_at",
                    "host_id",
                }
                and model._numeric_value(value) is not None
            }
            rows[split].append(
                {
                    "run_id": run_id.name,
                    "scenario_id": row.get("scenario_id"),
                    "load_profile": row.get("load_profile"),
                    "label": int(bool(row["ground_truth_anomalous"])),
                    "features": {
                        key: float(model._numeric_value(value))
                        for key, value in numeric.items()
                    },
                }
            )
    return rows


def _vectors(rows: list[dict[str, Any]], names: list[str]) -> np.ndarray:
    return np.array(
        [[row["features"].get(name, 0.0) for name in names] for row in rows],
        dtype=float,
    )


def _per_group(rows: list[dict[str, Any]], predictions: list[int], group: str) -> dict[str, Any]:
    groups: dict[str, dict[str, list[int]]] = {}
    for row, prediction in zip(rows, predictions):
        key = str(row.get(group) or "unknown")
        groups.setdefault(key, {"labels": [], "predictions": []})
        groups[key]["labels"].append(row["label"])
        groups[key]["predictions"].append(prediction)
    return {
        key: _binary_metrics(values["labels"], values["predictions"])
        for key, values in groups.items()
    }


def evaluate_configurations(raw_root: str) -> dict[str, Any]:
    model = BaselineAnomalyModel(raw_root)
    data = _rows(model)
    train, val, test = data["train"], data["val"], data["test"]
    feature_names = sorted({key for row in train + val + test for key in row["features"]})
    train_labels = [row["label"] for row in train]
    val_labels = [row["label"] for row in val]
    test_labels = [row["label"] for row in test]

    threshold_candidates = sorted({row["features"].get("linux_load_1m_mean", 0.0) for row in val})
    threshold_candidates = threshold_candidates or [0.0]
    threshold = float(max(
        threshold_candidates,
        key=lambda candidate: f1_score(
            val_labels,
            [int(row["features"].get("linux_load_1m_mean", 0.0) >= candidate) for row in val],
            zero_division=0,
        ),
    ))
    b0_predictions = [
        int(row["features"].get("linux_load_1m_mean", 0.0) >= threshold) for row in test
    ]

    classifier = RandomForestClassifier(
        random_state=42,
        n_estimators=200,
        class_weight="balanced",
    )
    classifier.fit(_vectors(train, feature_names), train_labels)
    b1_probabilities = classifier.predict_proba(_vectors(test, feature_names))[:, 1]
    b1_predictions = [int(probability >= 0.5) for probability in b1_probabilities]
    b2_predictions = [int(probability >= 0.5) for probability in b1_probabilities]
    eligible = int(sum(probability >= 0.8 for probability in b1_probabilities))

    return {
        "dataset_policy": "whole-run train/validation/test split",
        "feature_names": feature_names,
        "configurations": {
            "B0": {
                "description": "Linux load threshold baseline",
                "threshold_linux_load_1m": threshold,
                "metrics": _binary_metrics(test_labels, b0_predictions),
                "per_scenario": _per_group(test, b0_predictions, "scenario_id"),
                "per_load": _per_group(test, b0_predictions, "load_profile"),
            },
            "B1": {
                "description": "Linux telemetry Random Forest detection",
                "metrics": _binary_metrics(test_labels, b1_predictions),
                "per_scenario": _per_group(test, b1_predictions, "scenario_id"),
                "per_load": _per_group(test, b1_predictions, "load_profile"),
            },
            "B2": {
                "description": "B1 detection with policy confidence gate",
                "metrics": _binary_metrics(test_labels, b2_predictions),
                "mitigation_eligible_test_count": eligible,
                "mitigation_metrics": {
                    "detection_latency": "unavailable",
                    "mitigation_latency": "unavailable",
                    "recovery_time": "unavailable",
                    "reason": "No live response timeline is part of the offline pilot archive.",
                },
                "per_scenario": _per_group(test, b2_predictions, "scenario_id"),
                "per_load": _per_group(test, b2_predictions, "load_profile"),
            },
        },
    }