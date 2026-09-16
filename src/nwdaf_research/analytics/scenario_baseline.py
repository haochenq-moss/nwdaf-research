from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score

from nwdaf_research.preprocessing.features import RunFeatureBuilder


class ScenarioBaselineModel:
    """Simple run-level scenario classification baseline using verified metadata and Linux telemetry."""

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
        for run_dir in sorted(self.raw_root.joinpath("raw").iterdir()):
            if not run_dir.is_dir() or not run_dir.name.startswith("R"):
                continue
            features = self.feature_builder.build_features_for_run(run_dir.name)
            features["split"] = self.manifest["assignments"].get(run_dir.name, "unassigned")
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
                if key in {"run_id", "ground_truth_class", "ground_truth_anomalous", "ground_truth_scenario_id", "ground_truth_security", "ground_truth_severity", "split", "timeline_keys", "scenario_id", "load_profile", "created_at", "host_id"}:
                    continue
                numeric = self._numeric_value(value)
                if numeric is not None:
                    X[key] = numeric

            y = row["ground_truth_scenario_id"]
            dataset[split]["X"].append(X)
            dataset[split]["y"].append(y)

        return dataset

    def train_and_evaluate(self) -> dict[str, Any]:
        dataset = self.prepare_dataset()
        train_X = dataset["train"]["X"]
        train_y = dataset["train"]["y"]
        test_X = dataset["test"]["X"]
        test_y = dataset["test"]["y"]

        feature_names = sorted({key for row in train_X + test_X for key in row.keys()})
        X_train = np.array([[row.get(k, 0.0) for k in feature_names] for row in train_X], dtype=float)
        X_test = np.array([[row.get(k, 0.0) for k in feature_names] for row in test_X], dtype=float)

        model = RandomForestClassifier(random_state=42, n_estimators=200, class_weight="balanced")
        model.fit(X_train, train_y)
        preds = model.predict(X_test)

        return {
            "accuracy": accuracy_score(test_y, preds),
            "macro_f1": f1_score(test_y, preds, average="macro", zero_division=0),
            "test_count": len(test_y),
            "classes": sorted(set(test_y) | set(train_y)),
        }
