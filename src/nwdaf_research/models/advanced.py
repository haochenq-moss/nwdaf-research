from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class AdvancedEvaluation:
    best_params: dict[str, Any]
    seed_results: list[dict[str, Any]]
    calibrated: dict[str, Any]


def _metrics(labels: list[int], probabilities: np.ndarray) -> dict[str, float]:
    predictions = (probabilities >= 0.5).astype(int)
    return {
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "average_precision": float(average_precision_score(labels, probabilities)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
    }


def evaluate_advanced(
    train_x: np.ndarray,
    train_y: list[int],
    val_x: np.ndarray,
    val_y: list[int],
    test_x: np.ndarray,
    test_y: list[int],
    seeds: tuple[int, ...] = (7, 42, 123),
) -> AdvancedEvaluation:
    candidates = [
        {"n_estimators": 200, "max_depth": None, "class_weight": "balanced"},
        {"n_estimators": 300, "max_depth": 8, "class_weight": "balanced"},
        {"n_estimators": 300, "max_depth": 12, "class_weight": None},
    ]
    best_params = candidates[0]
    best_score = -1.0
    for params in candidates:
        model = Pipeline(
            [
                ("scale", StandardScaler()),
                ("classifier", RandomForestClassifier(random_state=42, **params)),
            ]
        )
        model.fit(train_x, train_y)
        score = f1_score(val_y, model.predict(val_x), zero_division=0)
        if score > best_score:
            best_score = score
            best_params = params

    seed_results = []
    for seed in seeds:
        model = Pipeline(
            [
                ("scale", StandardScaler()),
                ("classifier", RandomForestClassifier(random_state=seed, **best_params)),
            ]
        )
        model.fit(train_x, train_y)
        probabilities = model.predict_proba(test_x)[:, 1]
        seed_results.append({"seed": seed, **_metrics(test_y, probabilities)})

    calibrated_base = Pipeline(
        [
            ("scale", StandardScaler()),
            ("classifier", RandomForestClassifier(random_state=42, **best_params)),
        ]
    )
    calibrated = CalibratedClassifierCV(calibrated_base, method="sigmoid", cv=3)
    calibrated.fit(train_x, train_y)
    calibrated_probabilities = calibrated.predict_proba(test_x)[:, 1]
    return AdvancedEvaluation(
        best_params=best_params,
        seed_results=seed_results,
        calibrated=_metrics(test_y, calibrated_probabilities),
    )