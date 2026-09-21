#!/usr/bin/env python3
"""Run normalized, tuned, multi-seed, calibrated supplemental evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from nwdaf_research.analytics.baseline import BaselineAnomalyModel
from nwdaf_research.models.advanced import evaluate_advanced


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/supplemental_large_raw"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/advanced_supplemental.json"))
    args = parser.parse_args()
    model = BaselineAnomalyModel(args.root)
    dataset = model.prepare_dataset()
    names = sorted({key for split in dataset.values() for row in split["X"] for key in row})
    vector = lambda rows: np.asarray([[row.get(name, 0.0) for name in names] for row in rows], dtype=float)
    result = evaluate_advanced(
        vector(dataset["train"]["X"]), dataset["train"]["y"],
        vector(dataset["val"]["X"]), dataset["val"]["y"],
        vector(dataset["test"]["X"]), dataset["test"]["y"],
    )
    report = {"feature_names": names, "normalization": "StandardScaler fit on train only", "hyperparameter_search": True, "early_stopping": "GPU MLP backend only", "calibration": "sigmoid CalibratedClassifierCV", "result": {"best_params": result.best_params, "seed_results": result.seed_results, "calibrated": result.calibrated}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()