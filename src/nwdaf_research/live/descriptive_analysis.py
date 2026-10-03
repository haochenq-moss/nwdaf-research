from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Any

from nwdaf_research.live.analyst_review import prepare_pair_review
from nwdaf_research.live.benign_control import PLAN_SHA256


LOCK_SHA256 = "adac2105bb165e33551150aee14f5506bd5d26ac023b4cf444638cddd25fb8f5"


def analyze_held_out(root: str | Path, *, lock_path: str | Path, authorization_path: str | Path) -> dict[str, Any]:
    """Revalidate every planned pair before descriptive, non-model unblinding."""
    lock_bytes = Path(lock_path).read_bytes()
    auth_bytes = Path(authorization_path).read_bytes()
    lock = json.loads(lock_bytes)
    auth = json.loads(auth_bytes)
    if hashlib.sha256(lock_bytes).hexdigest() != LOCK_SHA256:
        raise ValueError("analysis lock changed")
    if not isinstance(auth, dict) or auth.get("schema_version") != "benign-descriptive-unblinding-v1":
        raise ValueError("invalid unblinding authorization")
    if auth.get("analysis_lock_sha256") != LOCK_SHA256 or auth.get("collection_plan_sha256") != PLAN_SHA256:
        raise ValueError("authorization lock/plan mismatch")
    if auth.get("allowed_pair_ids") != list(range(5, 13)) or auth.get("descriptive_unblinding_authorized") is not True:
        raise ValueError("all planned held-out pairs require explicit descriptive permission")
    if any(auth.get(name) is not False for name in (
        "training_authorized", "inference_authorized", "threshold_selection_authorized", "mitigation_authorized",
    )):
        raise ValueError("only descriptive analysis is permitted")
    results = []
    for pair_id in lock["held_out_pairs"]:
        pair = Path(root) / f"benign-control-held-out-pair{pair_id:02d}-20261003"
        row: dict[str, Any] = {"pair_id": pair_id, "endpoint": None, "integrity_status": "INVALID", "issues": []}
        try:
            packet = prepare_pair_review(pair, partition="held_out")
            if packet["pair_id"] != pair_id:
                raise ValueError("pair directory identity mismatch")
            if packet["parser_provenance"] != "matching_parser_file_hashes":
                raise ValueError("held-out pair lacks matching parser hashes")
            if not packet["collection_control_valid"]:
                raise ValueError("collection or synchronized control invalid")
            row.update(endpoint=packet["middle_sbi_event_count_delta"], integrity_status="VERIFIED",
                       execution_order=packet["execution_order"], artifact_sha256=packet["artifact_sha256"],
                       evidence_binding_sha256=packet["packet_binding_sha256"], label_review="not_performed")
            row["conditions"] = {}
            for condition in ("passive", "benign_nrf"):
                manifest = json.loads((pair / condition / "manifest.json").read_text())
                row["conditions"][condition] = {
                    "parser_sha256": manifest["parser_sha256"],
                    "windows": [
                        {"window_id": f"WBASE{index:03d}", "features": json.loads(
                            (pair / condition / "windows" / f"WBASE{index:03d}" / "readiness.json").read_text()
                        )["features"]} for index in range(1, 4)
                    ],
                }
            summary = json.loads((pair / "pair_summary.json").read_text())
            row["implementation_hashes"] = {name: summary[name] for name in (
                "collector_module_sha256", "control_module_sha256", "remote_code_sha256", "benign_remote_code_sha256",
            )}
            row["operation_receipt"] = packet["operation_receipt"]
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
            row.update(endpoint=None, integrity_status="INVALID", issues=[f"{type(error).__name__}: {error}"])
        results.append(row)
    endpoints = [row["endpoint"] for row in results if row["integrity_status"] == "VERIFIED"]
    strata: dict[str, list[int]] = {}
    for row in results:
        if row["integrity_status"] == "VERIFIED":
            binding = json.dumps({"implementation": row["implementation_hashes"], "parsers": {
                condition: values["parser_sha256"] for condition, values in row["conditions"].items()
            }}, sort_keys=True)
            strata.setdefault(hashlib.sha256(binding.encode()).hexdigest(), []).append(row["pair_id"])
    return {
        "schema_version": "benign-held-out-descriptive-results-v1", "analysis_lock_sha256": LOCK_SHA256,
        "authorization_sha256": hashlib.sha256(auth_bytes).hexdigest(), "collection_plan_sha256": PLAN_SHA256,
        "pairs": results, "planned_pair_count": 8, "verified_pair_count": len(endpoints),
        "invalid_pair_count": 8 - len(endpoints),
        "primary_endpoint_summary": {
            "paired_values": [{"pair_id": row["pair_id"], "value": row["endpoint"]} for row in results],
            "median": median(endpoints) if endpoints else None,
            "minimum": min(endpoints) if endpoints else None, "maximum": max(endpoints) if endpoints else None,
            "positive": sum(value > 0 for value in endpoints), "zero": sum(value == 0 for value in endpoints),
            "negative": sum(value < 0 for value in endpoints),
        },
        "implementation_strata": strata, "unblinded": True, "inference_performed": False,
        "model_approved": False, "actionable": False, "independent_review_completed": False,
        "interpretation": "Descriptive observability of known benign OAuth/discovery traffic in log-derived windows; not fuzz-triggered detection, vulnerability classification, model efficacy or mitigation evaluation.",
    }