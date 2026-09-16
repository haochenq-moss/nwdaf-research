from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from nwdaf_research.analytics.baseline import BaselineAnomalyModel
from nwdaf_research.provenance import build_model_manifest, write_manifest


class NWDAFResearchAnalyzer:
    """A minimal research-facing wrapper around the validated anomaly baseline."""

    def __init__(self, raw_root: str | Path, model_artifact: str | Path | None = None):
        self.raw_root = Path(raw_root)
        self.model = BaselineAnomalyModel(self.raw_root)
        self._trained_model = None
        self._feature_names: list[str] | None = None
        if model_artifact is not None:
            artifact_path = Path(model_artifact) / "model.pkl"
            if artifact_path.exists():
                with artifact_path.open("rb") as handle:
                    artifact = pickle.load(handle)
                self._trained_model = artifact["model"]
                self._feature_names = artifact["feature_names"]

    def _train_model(self) -> None:
        if self._trained_model is not None:
            return

        dataset = self.model.prepare_dataset()
        train_X = dataset["train"]["X"]
        train_y = dataset["train"]["y"]
        feature_names_all = sorted({key for row in train_X for key in row.keys()})
        X_train = np.array([[row.get(k, 0.0) for k in feature_names_all] for row in train_X], dtype=float)

        from sklearn.ensemble import RandomForestClassifier

        model = RandomForestClassifier(random_state=42, n_estimators=200, class_weight="balanced")
        model.fit(X_train, train_y)
        self._trained_model = model
        self._feature_names = feature_names_all

    def _vectorize_run(self, run_id: str) -> tuple[dict[str, float], list[str]]:
        row = self.model.feature_builder.build_features_for_run(run_id)
        split = self.model.manifest["assignments"].get(run_id, "unassigned")
        row["split"] = split

        X: dict[str, float] = {}
        for key, value in row.items():
            if key in {"run_id", "ground_truth_class", "ground_truth_anomalous", "ground_truth_scenario_id", "ground_truth_security", "ground_truth_severity", "split", "timeline_keys", "scenario_id", "load_profile", "created_at", "host_id"}:
                continue
            numeric_value = self.model._numeric_value(value)
            if numeric_value is not None:
                X[key] = numeric_value

        return X, sorted(X)

    def score_run(self, run_id: str) -> dict[str, Any]:
        self._train_model()
        X, feature_names = self._vectorize_run(run_id)
        result = self.score_features(X)

        return {
            "run_id": run_id,
            "predicted_label": result["predicted_label"],
            "anomaly_probability": result["anomaly_probability"],
            "feature_count": len(feature_names),
        }

    def score_features(self, features: dict[str, float]) -> dict[str, Any]:
        """Run the trained baseline on an externally supplied feature vector."""
        self._train_model()
        full_vector = np.array(
            [[float(features.get(key, 0.0)) for key in self._feature_names]],
            dtype=float,
        )
        probs = self._trained_model.predict_proba(full_vector)[0]
        anomaly_probability = float(probs[1]) if len(probs) > 1 else float(probs[0])
        return {
            "predicted_label": "ANOMALY" if anomaly_probability >= 0.5 else "NORMAL",
            "anomaly_probability": anomaly_probability,
            "confidence": max(anomaly_probability, 1.0 - anomaly_probability),
            "model_name": "random_forest",
            "model_version": "rf-v1",
            "feature_schema": "run-linux-v1",
        }

    def features_for_run(self, run_id: str) -> dict[str, float]:
        """Return the numeric feature vector derived from one verified run."""
        return self._vectorize_run(run_id)[0]

    def batch_score_runs(self, run_ids: list[str] | None = None) -> list[dict[str, Any]]:
        if run_ids is None:
            run_dir = self.model.feature_builder.raw_root
            run_ids = sorted(
                p.name for p in run_dir.iterdir() if p.is_dir() and p.name.startswith("R")
            )

        scores: list[dict[str, Any]] = []
        for run_id in run_ids:
            scores.append(self.score_run(run_id))
        return scores

    def export_batch_scores(self, output_path: str | Path | None = None) -> list[dict[str, Any]]:
        scores = self.batch_score_runs()
        if output_path is not None:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(scores, indent=2), encoding="utf-8")
        return scores

    def evaluate(self) -> dict[str, Any]:
        return self.model.train_and_evaluate()

    def save_model_artifact(self, output_dir: str | Path) -> dict[str, Any]:
        """Persist the fitted model and its evidence manifest for reproducible inference."""
        self._train_model()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        with (output_dir / "model.pkl").open("wb") as handle:
            pickle.dump(
                {
                    "model": self._trained_model,
                    "feature_names": self._feature_names,
                },
                handle,
            )
        repository_root = self.raw_root.resolve().parents[1]
        manifest = build_model_manifest(
            repository_root=repository_root,
            raw_root=self.raw_root,
            feature_names=list(self._feature_names or []),
            model_name="random_forest",
            model_version="rf-v1",
            random_seed=42,
        )
        write_manifest(output_dir / "manifest.json", manifest)
        return manifest
