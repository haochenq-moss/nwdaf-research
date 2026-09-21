from __future__ import annotations

import importlib.util
from typing import Any

import numpy as np


def linux_event_sequence(run_dir: str, max_length: int = 64) -> np.ndarray:
    """Create a fixed-length numeric sequence from real Linux event records."""
    import json
    from pathlib import Path

    rows = []
    path = Path(run_dir) / "linux" / "events.jsonl"
    if path.exists():
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    sequence = []
    for row in rows[-max_length:]:
        memory = row.get("memory_bytes") or {}
        total = float(memory.get("total", 0.0) or 0.0)
        available = float(memory.get("available", 0.0) or 0.0)
        sequence.append(
            [
                float(row.get("load_1m", 0.0) or 0.0),
                available / total if total else 0.0,
                float(row.get("cpu_count", 0.0) or 0.0),
            ]
        )
    while len(sequence) < max_length:
        sequence.insert(0, [0.0, 0.0, 0.0])
    return np.asarray(sequence, dtype=np.float32)


class TemporalGRUClassifier:
    """Optional CUDA GRU for event sequences; not used by the frozen baseline."""

    def __init__(self, input_size: int = 3, hidden_size: int = 32, epochs: int = 100):
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.epochs = epochs
        self.model = None
        self.head = None
        self.torch = None
        self.device = None

    @staticmethod
    def available() -> bool:
        if importlib.util.find_spec("torch") is None:
            return False
        import torch

        return bool(torch.cuda.is_available())

    def fit(self, sequences: np.ndarray, labels: list[int], validation: tuple[np.ndarray, list[int]] | None = None) -> None:
        if not self.available():
            raise RuntimeError("TemporalGRUClassifier requires a CUDA-enabled PyTorch environment")
        import torch
        from torch import nn

        self.torch = torch
        torch.manual_seed(42)
        device = torch.device("cuda")
        self.device = device
        self.model = nn.GRU(self.input_size, self.hidden_size, batch_first=True).to(device)
        self.head = nn.Linear(self.hidden_size, 2).to(device)
        optimizer = torch.optim.Adam(list(self.model.parameters()) + list(self.head.parameters()), lr=1e-3)
        labels_tensor = torch.tensor(labels, dtype=torch.long, device=device)
        sequence_tensor = torch.tensor(sequences, dtype=torch.float32, device=device)
        criterion = nn.CrossEntropyLoss()
        best_state: dict[str, Any] | None = None
        best_loss = float("inf")
        stale = 0
        for _ in range(self.epochs):
            self.model.train()
            optimizer.zero_grad(set_to_none=True)
            _, hidden = self.model(sequence_tensor)
            loss = criterion(self.head(hidden[-1]), labels_tensor)
            loss.backward()
            optimizer.step()
            if validation is not None:
                self.model.eval()
                val_x, val_y = validation
                with torch.no_grad():
                    vx = torch.tensor(val_x, dtype=torch.float32, device=device)
                    vy = torch.tensor(val_y, dtype=torch.long, device=device)
                    _, vh = self.model(vx)
                    val_loss = float(criterion(self.head(vh[-1]), vy).item())
                if val_loss < best_loss:
                    best_loss = val_loss
                    best_state = {"gru": self.model.state_dict(), "head": self.head.state_dict()}
                    stale = 0
                else:
                    stale += 1
                    if stale >= 15:
                        break
        if best_state:
            self.model.load_state_dict(best_state["gru"])
            self.head.load_state_dict(best_state["head"])

    def predict_proba(self, sequences: np.ndarray) -> np.ndarray:
        if self.model is None or self.head is None or self.torch is None:
            raise RuntimeError("TemporalGRUClassifier must be fitted first")
        self.model.eval()
        self.head.eval()
        with self.torch.no_grad():
            values = self.torch.tensor(sequences, dtype=self.torch.float32, device=self.device)
            _, hidden = self.model(values)
            return self.torch.softmax(self.head(hidden[-1]), dim=1).cpu().numpy()