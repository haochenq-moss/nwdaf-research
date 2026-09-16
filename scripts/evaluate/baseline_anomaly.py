#!/usr/bin/env python3
"""Evaluate the run-level anomaly baseline and save the measured metrics."""

from __future__ import annotations

import json
from pathlib import Path

from nwdaf_research.analytics.baseline import BaselineAnomalyModel


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    raw_root = repo_root / "data" / "raw"
    model = BaselineAnomalyModel(raw_root)
    metrics = model.train_and_evaluate()

    evaluation_dir = repo_root / "evaluation"
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = evaluation_dir / "baseline_anomaly_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
