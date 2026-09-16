from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RunFeatureBuilder:
    """Aggregate verified Linux telemetry and metadata into run-level features."""

    def __init__(self, raw_root: str | Path):
        root = Path(raw_root)
        self.raw_root = root / "raw" if (root / "raw").exists() else root

    def _read_json(self, path: Path) -> Any:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not path.exists():
            return rows
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                text = line.strip()
                if text:
                    rows.append(json.loads(text))
        return rows

    def _source_events(self, run_dir: Path, source: str) -> list[dict[str, Any]]:
        return self._read_jsonl(run_dir / source / "events.jsonl")

    def _flatten_memory(self, memory_obj: dict[str, Any] | None) -> tuple[float, float]:
        if not isinstance(memory_obj, dict):
            return 0.0, 0.0
        total = float(memory_obj.get("total", 0.0) or 0.0)
        available = float(memory_obj.get("available", 0.0) or 0.0)
        return total, available

    def build_features_for_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self.raw_root / run_id
        metadata = self._read_json(run_dir / "metadata.json")
        ground_truth = self._read_json(run_dir / "ground_truth.json")
        timeline = self._read_json(run_dir / "timeline.json")
        linux_events = self._read_jsonl(run_dir / "linux" / "events.jsonl")
        process_events = self._read_jsonl(run_dir / "linux" / "process_events.jsonl")
        sbi_events = self._source_events(run_dir, "sbi")
        pfcp_events = self._source_events(run_dir, "pfcp")
        free5gc_events = self._source_events(run_dir, "free5gc")
        ebpf_events = self._read_jsonl(run_dir / "linux" / "ebpf_events.jsonl")

        feature_row: dict[str, Any] = {
            "run_id": run_id,
            "scenario_id": metadata.get("scenario_id"),
            "load_profile": metadata.get("load_profile"),
            "created_at": metadata.get("created_at"),
            "duration_sec": float(metadata.get("duration_sec", 0.0) or 0.0),
            "host_id": metadata.get("host_id"),
            "split": None,
        }

        host_event_type_counts: dict[str, int] = {}
        process_event_type_counts: dict[str, int] = {}
        load_values: list[float] = []
        mem_total_values: list[float] = []
        mem_available_values: list[float] = []
        memory_ratios: list[float] = []

        if linux_events:
            for event in linux_events:
                event_type = event.get("event_type")
                if event_type is not None:
                    host_event_type_counts[event_type] = host_event_type_counts.get(event_type, 0) + 1
                if "load_1m" in event:
                    load_values.append(float(event.get("load_1m", 0.0) or 0.0))
                total, available = self._flatten_memory(event.get("memory_bytes"))
                mem_total_values.append(total)
                mem_available_values.append(available)
                if total > 0:
                    memory_ratios.append(available / total)

            mean_load = sum(load_values) / len(load_values) if load_values else 0.0
            mean_memory_total = sum(mem_total_values) / len(mem_total_values) if mem_total_values else 0.0
            mean_memory_available = sum(mem_available_values) / len(mem_available_values) if mem_available_values else 0.0
            load_variance = sum((value - mean_load) ** 2 for value in load_values) / len(load_values) if load_values else 0.0

            feature_row.update(
                {
                    "linux_event_count": len(linux_events),
                    "linux_load_1m_mean": mean_load,
                    "linux_load_1m_std": (load_variance ** 0.5) if load_values else 0.0,
                    "linux_load_1m_max": max(load_values) if load_values else 0.0,
                    "linux_load_1m_min": min(load_values) if load_values else 0.0,
                    "linux_memory_total_mean": mean_memory_total,
                    "linux_memory_available_mean": mean_memory_available,
                    "memory_available_ratio_mean": (sum(memory_ratios) / len(memory_ratios)) if memory_ratios else 0.0,
                    "host_event_type_counts": host_event_type_counts,
                }
            )
        else:
            feature_row.update({
                "linux_event_count": 0,
                "linux_load_1m_mean": 0.0,
                "linux_load_1m_std": 0.0,
                "linux_load_1m_max": 0.0,
                "linux_load_1m_min": 0.0,
                "linux_memory_total_mean": 0.0,
                "linux_memory_available_mean": 0.0,
                "memory_available_ratio_mean": 0.0,
                "host_event_type_counts": {},
            })

        for event in process_events:
            event_type = event.get("event_type")
            if event_type is not None:
                process_event_type_counts[event_type] = process_event_type_counts.get(event_type, 0) + 1

        feature_row.update({
            "process_event_count": len(process_events),
            "process_event_by_type": process_event_type_counts,
            "sbi_event_count": len(sbi_events),
            "pfcp_event_count": len(pfcp_events),
            "free5gc_event_count": len(free5gc_events),
            "ebpf_event_count": len(ebpf_events),
            "sbi_telemetry_available": float(bool(sbi_events)),
            "pfcp_telemetry_available": float(bool(pfcp_events)),
            "free5gc_telemetry_available": float(bool(free5gc_events)),
            "ebpf_telemetry_available": float(bool(ebpf_events)),
            "sbi_error_event_count": sum(
                1 for event in sbi_events
                if isinstance(event.get("status"), int) and event["status"] >= 400
            ),
            "pfcp_request_count": sum(
                1 for event in pfcp_events if event.get("direction") == "request"
            ),
            "pfcp_response_count": sum(
                1 for event in pfcp_events if event.get("direction") == "response"
            ),
            "timeline_keys": list(timeline.get("timeline", {}).keys()) if isinstance(timeline, dict) else [],
            "ground_truth_class": ground_truth.get("class"),
            "ground_truth_anomalous": bool(ground_truth.get("anomalous", False)),
            "ground_truth_scenario_id": ground_truth.get("scenario_id"),
            "ground_truth_security": bool(ground_truth.get("security", False)),
            "ground_truth_severity": ground_truth.get("severity"),
        })

        return feature_row
