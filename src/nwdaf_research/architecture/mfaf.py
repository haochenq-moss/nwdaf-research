from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelRecord:
    name: str
    version: str
    artifact_path: str
    manifest: dict[str, Any]


class MFAFRegistry:
    """Research model lifecycle registry for approved model artifacts."""

    def __init__(self):
        self._records: dict[tuple[str, str], ModelRecord] = {}

    def register(self, artifact_dir: str | Path) -> ModelRecord:
        directory = Path(artifact_dir)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        model = manifest["model"]
        record = ModelRecord(
            name=model["name"],
            version=model["version"],
            artifact_path=str(directory / "model.pkl"),
            manifest=manifest,
        )
        self._records[(record.name, record.version)] = record
        return record

    def get(self, name: str, version: str) -> ModelRecord:
        return self._records[(name, version)]

    def activate(self, name: str, version: str) -> ModelRecord:
        record = self.get(name, version)
        if not Path(record.artifact_path).exists():
            raise FileNotFoundError(record.artifact_path)
        self._active = record
        return record

    @property
    def active(self) -> ModelRecord | None:
        return getattr(self, "_active", None)

    def list(self) -> list[ModelRecord]:
        return list(self._records.values())