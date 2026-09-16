from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from nwdaf_research.preprocessing.features import RunFeatureBuilder


class BaselineAnomalyModel:
    """Simple run-level anomaly baseline using verified Linux telemetry and metadata."""

    def __init__(self, raw_root: str | Path):
        self.raw_root = Path(raw_root)
        self.feature_builder = RunFeatureBuilder(self.raw_root)
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> dict[str, Any]:
        manifest_path = self.raw_root / "split_manifest.json"
        if not manifest_path.exists():
            manifest_path = self.raw_root / "_split_manifest.json"
        with manifest_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _build_run_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for run_id in sorted(self.feature_builder.raw_root.iterdir() if self.feature_builder.raw_root.exists() else []):
            if not run_id.is_dir() or not run_id.name.startswith("R"):
                continue
            features = self.feature_builder.build_features_for_run(run_id.name)
            split = self.manifest["assignments"].get(run_id.name, "unassigned")
            features["split"] = split
            rows.append(features)
        return rows

    @staticmethod
    def _numeric_value(value: Any) -> float | None:
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def prepare_dataset(self) -> dict[str, dict[str, Any]]:
        rows = self._build_run_rows()
        dataset: dict[str, dict[str, Any]] = {"train": {"X": [], "y": []}, "val": {"X": [], "y": []}, "test": {"X": [], "y": []}}

        for row in rows:
            split = row["split"]
            if split not in dataset:
                continue

            X = {}
            for key, value in row.items():
                if key in {"run_id", "ground_truth_class", "ground_truth_anomalous", "ground_truth_scenario_id", "ground_truth_security", "ground_truth_severity", "split", "timeline_keys", "scenario_id", "load_profile", "created_at", "host_id", "ground_truth_scenario_id", "ground_truth_severity", "ground_truth_security"}:
                    continue
                numeric_value = self._numeric_value(value)
                if numeric_value is not None:
                    X[key] = numeric_value

            y = int(bool(row["ground_truth_anomalous"]))
            dataset[split]["X"].append(X)
            dataset[split]["y"].append(y)

        return dataset

    def _evaluate_with_feature_subset(self, feature_names: list[str]) -> dict[str, Any]:
        dataset = self.prepare_dataset()
        train_X = dataset["train"]["X"]
        train_y = dataset["train"]["y"]
        test_X = dataset["test"]["X"]
        test_y = dataset["test"]["y"]

        X_train = np.array([[row.get(k, 0.0) for k in feature_names] for row in train_X], dtype=float)
        X_test = np.array([[row.get(k, 0.0) for k in feature_names] for row in test_X], dtype=float)

        model = RandomForestClassifier(random_state=42, n_estimators=200, class_weight="balanced")
        model.fit(X_train, train_y)
        preds = model.predict(X_test)

        return {
            "accuracy": accuracy_score(test_y, preds),
            "f1": f1_score(test_y, preds, zero_division=0),
            "test_count": len(test_y),
            "positive_rate": float(np.mean(test_y)),
        }

    def evaluate_feature_ablation(self) -> dict[str, dict[str, Any]]:
        dataset = self.prepare_dataset()
        all_feature_names = sorted({key for row in dataset["train"]["X"] + dataset["val"]["X"] + dataset["test"]["X"] for key in row.keys()})

        feature_groups: dict[str, list[str]] = {
            "full": all_feature_names,
            "linux_load": [name for name in all_feature_names if name.startswith("linux_load_")],
            "memory": [name for name in all_feature_names if "memory" in name.lower() or name == "memory_available_ratio_mean"],
            "runtime": [name for name in all_feature_names if name in {"duration_sec", "linux_event_count", "process_event_count", "linux_load_1m_mean", "linux_load_1m_std"}],
        }

        results: dict[str, dict[str, Any]] = {}
        for group_name, feature_names in feature_groups.items():
            if not feature_names:
                results[group_name] = {"accuracy": 0.0, "f1": 0.0, "test_count": len(dataset["test"]["y"]), "positive_rate": float(np.mean(dataset["test"]["y"]))}
                continue
            results[group_name] = self._evaluate_with_feature_subset(feature_names)

        return results

    def train_and_evaluate(self) -> dict[str, Any]:
        dataset = self.prepare_dataset()
        train_X = dataset["train"]["X"]
        train_y = dataset["train"]["y"]
        val_X = dataset["val"]["X"]
        val_y = dataset["val"]["y"]
        test_X = dataset["test"]["X"]
        test_y = dataset["test"]["y"]

        feature_names = sorted({key for row in train_X + val_X + test_X for key in row.keys()})

        X_train = np.array([[row.get(k, 0.0) for k in feature_names] for row in train_X], dtype=float)
        X_val = np.array([[row.get(k, 0.0) for k in feature_names] for row in val_X], dtype=float)
        X_test = np.array([[row.get(k, 0.0) for k in feature_names] for row in test_X], dtype=float)

        model = RandomForestClassifier(random_state=42, n_estimators=200, class_weight="balanced")
        model.fit(X_train, train_y)
        preds = model.predict(X_test)

        metrics = {
            "accuracy": accuracy_score(test_y, preds),
            "f1": f1_score(test_y, preds, zero_division=0),
            "test_count": len(test_y),
            "positive_rate": float(np.mean(test_y)),
        }
        return metrics
