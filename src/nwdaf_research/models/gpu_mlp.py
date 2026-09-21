from __future__ import annotations

import importlib.util
import platform
import time
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class GPUTrainingResult:
    model_name: str
    device: str
    epochs: int
    train_seconds: float
    inference_seconds: float
    test_accuracy: float
    test_f1: float
    torch_version: str
    cuda_version: str | None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class GPUMLPClassifier:
    """Small CUDA MLP backend for explicit GPU experiments.

    This is optional by design: PyTorch is imported lazily because CUDA builds
    are cluster-specific and should not be forced into the CPU research env.
    """

    def __init__(self, input_size: int, seed: int = 42, epochs: int = 100):
        self.input_size = input_size
        self.seed = seed
        self.epochs = epochs
        self._torch = None
        self._model = None
        self._device = None

    @staticmethod
    def available() -> bool:
        if importlib.util.find_spec("torch") is None:
            return False
        import torch

        return bool(torch.cuda.is_available())

    def _load(self) -> None:
        if importlib.util.find_spec("torch") is None:
            raise RuntimeError("PyTorch is not installed in this environment")
        import torch
        from torch import nn

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; submit this workload through Slurm")
        torch.manual_seed(self.seed)
        torch.cuda.manual_seed_all(self.seed)
        self._torch = torch
        self._device = torch.device("cuda")
        self._model = nn.Sequential(
            nn.Linear(self.input_size, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 2),
        ).to(self._device)

    def fit(
        self,
        x_train: np.ndarray,
        y_train: list[int],
        x_val: np.ndarray | None = None,
        y_val: list[int] | None = None,
        patience: int = 15,
    ) -> "GPUMLPClassifier":
        self._load()
        torch = self._torch
        from torch import nn

        features = torch.tensor(x_train, dtype=torch.float32, device=self._device)
        labels = torch.tensor(y_train, dtype=torch.long, device=self._device)
        optimizer = torch.optim.Adam(self._model.parameters(), lr=1e-3)
        class_counts = np.bincount(np.asarray(y_train, dtype=int), minlength=2)
        weights = len(y_train) / np.maximum(class_counts, 1)
        criterion = nn.CrossEntropyLoss(
            weight=torch.tensor(weights, dtype=torch.float32, device=self._device)
        )
        best_state = None
        best_loss = float("inf")
        stale_epochs = 0
        self._model.train()
        for _ in range(self.epochs):
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(self._model(features), labels)
            loss.backward()
            optimizer.step()
            if x_val is not None and y_val is not None:
                self._model.eval()
                with torch.no_grad():
                    validation = torch.tensor(x_val, dtype=torch.float32, device=self._device)
                    validation_labels = torch.tensor(y_val, dtype=torch.long, device=self._device)
                    validation_loss = float(criterion(self._model(validation), validation_labels).item())
                self._model.train()
                if validation_loss < best_loss:
                    best_loss = validation_loss
                    best_state = {key: value.detach().clone() for key, value in self._model.state_dict().items()}
                    stale_epochs = 0
                else:
                    stale_epochs += 1
                    if stale_epochs >= patience:
                        break
        if best_state is not None:
            self._model.load_state_dict(best_state)
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("GPUMLPClassifier must be fitted before inference")
        torch = self._torch
        self._model.eval()
        with torch.no_grad():
            values = torch.tensor(features, dtype=torch.float32, device=self._device)
            return torch.softmax(self._model(values), dim=1).detach().cpu().numpy()

    def train_evaluate(
        self,
        x_train: np.ndarray,
        y_train: list[int],
        x_test: np.ndarray,
        y_test: list[int],
        x_val: np.ndarray | None = None,
        y_val: list[int] | None = None,
    ) -> GPUTrainingResult:
        from sklearn.metrics import accuracy_score, f1_score

        start = time.perf_counter()
        self.fit(x_train, y_train, x_val=x_val, y_val=y_val)
        train_seconds = time.perf_counter() - start
        if self._torch is not None:
            self._torch.cuda.synchronize()
        start = time.perf_counter()
        probabilities = self.predict_proba(x_test)
        if self._torch is not None:
            self._torch.cuda.synchronize()
        inference_seconds = time.perf_counter() - start
        predictions = np.argmax(probabilities, axis=1)
        return GPUTrainingResult(
            model_name="cuda_mlp",
            device=str(self._device),
            epochs=self.epochs,
            train_seconds=train_seconds,
            inference_seconds=inference_seconds,
            test_accuracy=float(accuracy_score(y_test, predictions)),
            test_f1=float(f1_score(y_test, predictions, zero_division=0)),
            torch_version=str(self._torch.__version__),
            cuda_version=getattr(self._torch.version, "cuda", None),
        )