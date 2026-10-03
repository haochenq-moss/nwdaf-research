from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from nwdaf_research.input_testing.records import _parse_timestamp


STAGES = (
    "software_outcome", "network_observation", "protocol_state_review",
    "cleanup_review", "telemetry_bundle", "analyst_decision",
)


def inspect_case_evidence(bundle_dir: str | Path) -> dict[str, Any]:
    """Check externally collected evidence references; never execute or authorize a test."""
    root = Path(bundle_dir).resolve()
    manifest = json.loads((root / "case_evidence.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "fuzz-case-evidence-v1":
        raise ValueError("unsupported case evidence schema")
    for name in ("input_id", "run_id"):
        if not isinstance(manifest.get(name), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", manifest[name]):
            raise ValueError(f"invalid {name}")
    commit = manifest.get("free5gc_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        raise ValueError("pinned free5gc_commit required")
    start = _parse_timestamp("window_start", manifest.get("window_start"))
    end = _parse_timestamp("window_end", manifest.get("window_end"))
    if end <= start:
        raise ValueError("invalid observation window")

    def artifact(reference: Any) -> Path:
        if not isinstance(reference, dict):
            raise ValueError("artifact reference must be an object")
        relative = reference.get("path")
        digest = reference.get("sha256")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("unsafe artifact path")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("artifact absent or outside bundle")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid artifact SHA-256")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("artifact hash mismatch")
        return path

    blockers = []
    try:
        artifact(manifest.get("input"))
        input_status = "HASH_VERIFIED"
    except (OSError, ValueError) as error:
        input_status = "UNVERIFIED"
        blockers.append(f"input: {error}")
    stages = manifest.get("stages", {})
    if not isinstance(stages, dict) or set(stages) - set(STAGES):
        raise ValueError("invalid or unknown evidence stages")
    results = {}
    for name in STAGES:
        stage = stages.get(name)
        if stage is None:
            results[name] = {"status": "MISSING"}
            blockers.append(f"{name}: missing evidence")
            continue
        try:
            path = artifact(stage)
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError("stage record must be a JSON object")
            for key in ("input_id", "run_id", "free5gc_commit"):
                if record.get(key) != manifest[key]:
                    raise ValueError(f"stage {key} mismatch")
            if record.get("input_sha256") != manifest["input"]["sha256"]:
                raise ValueError("stage input hash mismatch")
            if not isinstance(record.get("evidence_refs"), list) or not record["evidence_refs"]:
                raise ValueError("supporting evidence references required")
            for reference in record["evidence_refs"]:
                artifact(reference)
            if name in {"protocol_state_review", "cleanup_review", "analyst_decision"}:
                if not isinstance(record.get("reviewer_id"), str) or not record["reviewer_id"].strip():
                    raise ValueError("reviewer identity required")
                reviewed_at = _parse_timestamp("reviewed_at", record.get("reviewed_at"))
                if reviewed_at < end:
                    raise ValueError("review precedes observation completion")
                if record.get("decision") != "approved":
                    raise ValueError("review is not approved")
                if not isinstance(record.get("rationale"), str) or not record["rationale"].strip():
                    raise ValueError("review rationale required")
            else:
                observed_start = _parse_timestamp("window_start", record.get("window_start"))
                observed_end = _parse_timestamp("window_end", record.get("window_end"))
                if observed_end <= observed_start:
                    raise ValueError("invalid stage observation interval")
                if name == "network_observation" and not start <= observed_start < observed_end <= end:
                    raise ValueError("network observation outside case window")
                if name == "telemetry_bundle" and not observed_start <= start < end <= observed_end:
                    raise ValueError("telemetry does not bracket case window")
                if not isinstance(record.get("observed_outcome"), str) or not record["observed_outcome"].strip():
                    raise ValueError("independently recorded outcome required")
            results[name] = {"status": "REFERENCES_VERIFIED", "path": stage["path"]}
        except (OSError, ValueError, KeyError, TypeError) as error:
            results[name] = {"status": "UNVERIFIED", "issue": str(error)}
            blockers.append(f"{name}: {error}")
    return {
        "schema_version": "fuzz-case-evidence-check-v1", "input_id": manifest["input_id"],
        "run_id": manifest["run_id"], "input_status": input_status, "stages": results,
        "evidence_chain_status": "REFERENCES_COMPLETE" if not blockers else "INCOMPLETE",
        "blockers": blockers, "evidence_authenticity_verified": False,
        "reviewer_independence_verified": False, "protocol_correctness_established": False,
        "fuzz_triggered_detection_demonstrated": False, "network_transmission_executed": False,
        "actionable": False,
        "interpretation": "Reference integrity only; external observations and expert review remain necessary. No test execution, vulnerability reproduction, model scoring or mitigation is performed.",
    }