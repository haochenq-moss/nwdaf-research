#!/usr/bin/env python3
"""Train the optional CUDA GRU on real Linux event sequences."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, f1_score

from nwdaf_research.models.temporal_gru import TemporalGRUClassifier, linux_event_sequence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/supplemental_large_raw"))
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--max-length", type=int, default=64)
    parser.add_argument("--output", type=Path, default=Path("$HOME/temporal_gru_result.json"))
    args = parser.parse_args()
    manifest = json.loads((args.root / "_split_manifest.json").read_text(encoding="utf-8"))
    groups = {"train": ([], []), "val": ([], []), "test": ([], [])}
    for run_dir in sorted(args.root.glob("R*")):
        if not run_dir.is_dir():
            continue
        ground_truth = json.loads((run_dir / "ground_truth.json").read_text(encoding="utf-8"))
        sequence = linux_event_sequence(str(run_dir), max_length=args.max_length)
        label = int(bool(ground_truth.get("anomalous", False)))
        sequences, labels = groups[manifest["assignments"][run_dir.name]]
        sequences.append(sequence)
        labels.append(label)
    model = TemporalGRUClassifier(epochs=args.epochs)
    model.fit(np.asarray(groups["train"][0]), groups["train"][1], (np.asarray(groups["val"][0]), groups["val"][1]))
    probabilities = model.predict_proba(np.asarray(groups["test"][0]))[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    report = {
        "model": "cuda_temporal_gru",
        "device": str(model.device),
        "torch_version": str(model.torch.__version__),
        "cuda_version": model.torch.version.cuda,
        "epochs": args.epochs,
        "max_sequence_length": args.max_length,
        "train_count": len(groups["train"][1]),
        "validation_count": len(groups["val"][1]),
        "test_count": len(groups["test"][1]),
        "accuracy": float(accuracy_score(groups["test"][1], predictions)),
        "f1": float(f1_score(groups["test"][1], predictions, zero_division=0)),
    }
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()