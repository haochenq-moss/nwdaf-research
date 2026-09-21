#!/usr/bin/env python3
"""Train and measure the optional CUDA MLP backend on a Slurm GPU node."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np

from nwdaf_research.analytics.baseline import BaselineAnomalyModel
from nwdaf_research.models.gpu_mlp import GPUMLPClassifier


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--backend", choices=("torch", "cpu"), default=os.environ.get("GPU_BACKEND", "torch"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/gpu_mlp.json"))
    args = parser.parse_args()

    baseline = BaselineAnomalyModel(args.raw_root)
    dataset = baseline.prepare_dataset()
    names = sorted({key for row in dataset["train"]["X"] + dataset["test"]["X"] for key in row})
    x_train = np.asarray([[row.get(name, 0.0) for name in names] for row in dataset["train"]["X"]], dtype=np.float32)
    x_test = np.asarray([[row.get(name, 0.0) for name in names] for row in dataset["test"]["X"]], dtype=np.float32)
    if args.backend == "cpu":
        from sklearn.neural_network import MLPClassifier
        from sklearn.metrics import accuracy_score, f1_score
        import time
        started = time.perf_counter()
        model = MLPClassifier(hidden_layer_sizes=(64, 32), random_state=42, max_iter=args.epochs)
        model.fit(x_train, dataset["train"]["y"])
        train_seconds = time.perf_counter() - started
        started = time.perf_counter()
        predictions = model.predict(x_test)
        inference_seconds = time.perf_counter() - started
        result = {
            "model_name": "cpu_mlp_fallback",
            "device": "cpu",
            "epochs": args.epochs,
            "train_seconds": train_seconds,
            "inference_seconds": inference_seconds,
            "test_accuracy": float(accuracy_score(dataset["test"]["y"], predictions)),
            "test_f1": float(f1_score(dataset["test"]["y"], predictions, zero_division=0)),
            "torch_version": None,
            "cuda_version": None,
        }
    else:
        result = GPUMLPClassifier(len(names), epochs=args.epochs).train_evaluate(
            x_train, dataset["train"]["y"], x_test, dataset["test"]["y"]
        ).as_dict()
    report = {"backend": args.backend, "feature_names": names, "result": result}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()