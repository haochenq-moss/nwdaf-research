from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DatasetLoader:
    """Load the verified run-based dataset from the extracted raw directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.raw_dir = self.root / "raw" if (self.root / "raw").exists() else self.root
        self.split_manifest_path = self.root / "split_manifest.json"
        if not self.split_manifest_path.exists():
            self.split_manifest_path = self.root / "_split_manifest.json"

    def discover_runs(self) -> list[str]:
        if not self.raw_dir.exists():
            raise FileNotFoundError(f"Raw dataset directory not found: {self.raw_dir}")
        return sorted(p.name for p in self.raw_dir.iterdir() if p.is_dir() and p.name.startswith("R"))

    def load_json(self, path: Path) -> Any:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def load_jsonl(self, path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not path.exists():
            return rows

        with path.open("r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Malformed JSON in {path} at line {line_number}: {exc}") from exc
                rows.append(row)
        return rows

    def load_split_manifest(self) -> dict[str, Any]:
        if not self.split_manifest_path.exists():
            raise FileNotFoundError(f"Split manifest not found: {self.split_manifest_path}")
        return self.load_json(self.split_manifest_path)

    def load_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self.raw_dir / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir}")

        metadata = self.load_json(run_dir / "metadata.json")
        ground_truth = self.load_json(run_dir / "ground_truth.json")
        timeline = self.load_json(run_dir / "timeline.json")

        telemetry: dict[str, Any] = {}
        for source_name in ["linux", "free5gc", "pfcp", "sbi"]:
            source_dir = run_dir / source_name
            if not source_dir.exists():
                continue
            event_path = source_dir / "events.jsonl"
            telemetry[source_name] = self.load_jsonl(event_path)

        split_manifest = self.load_split_manifest()
        split = split_manifest["assignments"].get(run_id, "unassigned")

        return {
            "run_id": run_id,
            "metadata": metadata,
            "ground_truth": ground_truth,
            "timeline": timeline,
            "telemetry": telemetry,
            "split": split,
        }
