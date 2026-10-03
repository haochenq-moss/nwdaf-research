from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from nwdaf_research.live.passive_campaign import process_capture
from nwdaf_research.live.telemetry_window import BASELINE_CONTRACT, TelemetryWindow


def summarize_baseline_campaigns(campaign_dirs: list[str | Path]) -> dict[str, Any]:
    """Recompute passive evidence and summarize features without training or scoring."""
    if not campaign_dirs:
        raise ValueError("at least one campaign is required")
    campaigns = []
    ready_rows = []
    seen_paths: set[Path] = set()
    seen_hashes: set[str] = set()
    feature_names = TelemetryWindow("2026-10-03T00:00:00Z", contract=BASELINE_CONTRACT).feature_names
    for directory in campaign_dirs:
        root = Path(directory).resolve()
        if root in seen_paths:
            raise ValueError("duplicate campaign path")
        seen_paths.add(root)
        capture_bytes = (root / "capture.json").read_bytes()
        digest = hashlib.sha256(capture_bytes).hexdigest()
        if digest in seen_hashes:
            raise ValueError("duplicate capture evidence")
        seen_hashes.add(digest)
        capture = json.loads(capture_bytes)
        result = process_capture(
            capture, window_count=capture["window_count"], duration_sec=capture["duration_sec"],
        )
        if json.loads((root / "report.json").read_text(encoding="utf-8")) != result["report"]:
            raise ValueError(f"saved report disagrees with capture: {root.name}")
        artifact_hashes = {"capture.json": digest}
        for filename in ("manifest.json", "report.json"):
            artifact_hashes[filename] = hashlib.sha256((root / filename).read_bytes()).hexdigest()
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        for key in ("contract", "hostname", "boot_id", "git_revision", "clock_domain", "collector_instance_id"):
            if manifest.get(key) != capture.get(key):
                raise ValueError(f"manifest identity disagrees with capture: {root.name}/{key}")
        if manifest.get("parser_sha256") != capture.get("parser_sha256"):
            raise ValueError(f"manifest parser hashes disagree with capture: {root.name}")
        window_rows = []
        for window in result["windows"]:
            window_id = window["metadata"]["window_id"]
            folder = root / "windows" / window_id
            for filename, expected in (("metadata.json", window["metadata"]), ("readiness.json", window["readiness"])):
                content = (folder / filename).read_bytes()
                if json.loads(content) != expected:
                    raise ValueError(f"saved window disagrees with capture: {root.name}/{window_id}/{filename}")
                artifact_hashes[f"windows/{window_id}/{filename}"] = hashlib.sha256(content).hexdigest()
            stream = (folder / "snapshots.jsonl").read_bytes()
            if [json.loads(line) for line in stream.splitlines() if line.strip()] != window["stream"]:
                raise ValueError(f"saved snapshots disagree with capture: {root.name}/{window_id}")
            artifact_hashes[f"windows/{window_id}/snapshots.jsonl"] = hashlib.sha256(stream).hexdigest()
            readiness = window["readiness"]
            features = readiness["features"]
            if readiness["status"] == "READY":
                if set(features) != set(feature_names) or any(
                    isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                    for value in features.values()
                ):
                    raise ValueError("invalid ready baseline feature vector")
                ready_rows.append(features)
            window_rows.append({"window_id": window_id, "status": readiness["status"], "features": features})
        campaigns.append({
            "campaign_id": root.name, "capture_sha256": digest,
            "condition": capture.get("condition", "passive"),
            "parser_sha256": capture.get("parser_sha256"),
            "evaluation_group": digest,
            "hostname": capture["hostname"], "boot_id": capture["boot_id"],
            "free5gc_commit": capture["git_revision"], "status": result["report"]["status"],
            "blockers": result["report"]["blockers"], "artifact_sha256": artifact_hashes,
            "windows": window_rows, "label_review": "not_performed",
        })
    statistics = {
        name: {
            "min": min(row[name] for row in ready_rows), "max": max(row[name] for row in ready_rows),
            "mean": mean(row[name] for row in ready_rows),
            "population_std": pstdev(row[name] for row in ready_rows),
        }
        for name in feature_names
    } if ready_rows else {}
    return {
        "schema_version": "baseline-evidence-summary-v1", "contract": BASELINE_CONTRACT,
        "campaigns": campaigns, "campaign_count": len(campaigns),
        "ready_window_count": len(ready_rows), "feature_statistics": statistics,
        "inference_performed": False, "evaluation_ready": False, "actionable": False,
        "limitations": [
            "Declared condition labels have not been independently reviewed.",
            "Consecutive windows are correlated; keep each capture group in one evaluation partition.",
            "This block summary does not validate pair linkage; use the separate pair journal and synchronization receipt. No confirmed-case condition is established.",
            "Feature variation is not an anomaly-score distribution or detection-quality result.",
            "Artifact hashes support identity checking, not proof of authenticity.",
        ],
    }