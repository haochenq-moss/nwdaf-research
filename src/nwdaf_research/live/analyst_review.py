from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from nwdaf_research.live.baseline_evidence import summarize_baseline_campaigns
from nwdaf_research.live.benign_control import PLAN_SHA256
from nwdaf_research.live.telemetry_window import parse_time


REVIEW_CHECKS = (
    "artifact_identity", "window_integrity", "operation_synchronization",
    "fixture_and_label_basis", "provenance_limitations", "background_activity_limits",
)


def _binding(document: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def prepare_pair_review(pair_dir: str | Path, *, partition: str = "pilot") -> dict[str, Any]:
    """Bind a pending review to recomputed evidence without approving any label."""
    root = Path(pair_dir).resolve()
    journal = json.loads((root / "pair.json").read_text(encoding="utf-8"))
    summary = json.loads((root / "pair_summary.json").read_text(encoding="utf-8"))
    plan_bytes = (root / "frozen_plan.json").read_bytes()
    if hashlib.sha256(plan_bytes).hexdigest() != PLAN_SHA256 or journal.get("plan_sha256") != PLAN_SHA256:
        raise ValueError("frozen plan hash mismatch")
    if not isinstance(journal, dict) or not isinstance(summary, dict) or any(summary.get(key) != value for key, value in journal.items()):
        raise ValueError("pair journal and summary disagree")
    pair_id = journal.get("pair_id")
    allowed = range(1, 5) if partition == "pilot" else range(5, 13)
    if partition not in {"pilot", "held_out"} or type(pair_id) is not int or pair_id not in allowed or journal.get("split") != partition:
        raise ValueError("review packet partition mismatch")
    plan = json.loads(plan_bytes)
    first = plan["schedule"]["first_condition"][pair_id - 1]
    order = [first, "passive" if first == "benign_nrf" else "benign_nrf"]
    if journal.get("condition_order") != order or journal.get("executed_conditions") != order:
        raise ValueError("pair execution order does not match frozen plan")
    evidence = summarize_baseline_campaigns([root / condition for condition in order])
    campaigns = {row["condition"]: row for row in evidence["campaigns"]}
    if set(campaigns) != {"passive", "benign_nrf"}:
        raise ValueError("pair conditions are missing or duplicated")
    manifests = {condition: json.loads((root / condition / "manifest.json").read_text()) for condition in order}
    fixture_keys = ("hostname", "boot_id", "git_revision", "parser_paths", "contract", "clock_domain", "warmup_sec", "window_count", "nominal_duration_sec", "read_budget")
    if any(manifests[order[0]][key] != manifests[order[1]][key] for key in fixture_keys):
        raise ValueError("pair fixture mismatch")
    hashes = campaigns["passive"]["parser_sha256"]
    provenance = "legacy_missing_parser_hashes" if hashes is None else "matching_parser_file_hashes"
    if hashes != campaigns["benign_nrf"]["parser_sha256"]:
        raise ValueError("pair parser hashes mismatch")
    benign = json.loads((root / "benign_nrf" / "report.json").read_text())
    valid = all(row["status"] == "READY" for row in campaigns.values()) and benign.get("control_valid") is True
    delta = None
    if valid:
        middle = {condition: next(row for row in campaign["windows"] if row["window_id"] == "WBASE002")
                  for condition, campaign in campaigns.items()}
        delta = middle["benign_nrf"]["features"]["sbi_event_count"] - middle["passive"]["features"]["sbi_event_count"]
    if summary.get("control_valid") is not valid or summary.get("middle_sbi_event_count_delta") != delta:
        raise ValueError("saved pair validity or delta disagrees with raw evidence")
    artifacts = {
        filename: hashlib.sha256((root / filename).read_bytes()).hexdigest()
        for filename in ("pair.json", "pair_summary.json", "frozen_plan.json")
    }
    for campaign in evidence["campaigns"]:
        artifacts.update({f'{campaign["condition"]}/{name}': digest for name, digest in campaign["artifact_sha256"].items()})
    packet = {
        "schema_version": "benign-pair-review-packet-v1", "pair_id": pair_id,
        "attempt_id": journal["attempt_id"], "evaluation_group": journal["group"],
        "split": partition, "plan_sha256": PLAN_SHA256, "artifact_sha256": artifacts,
        "execution_order": order, "collection_control_valid": valid,
        "middle_sbi_event_count_delta": delta, "parser_provenance": provenance,
        "operation_receipt": benign["operation_receipt"],
        "review_status": "PENDING", "label_review": "not_performed",
        "required_checks": list(REVIEW_CHECKS), "inference_performed": False,
        "model_approved": False, "actionable": False,
        "limitations": [
            "Automated revalidation is not independent analyst review.",
            "Declared benign/passive conditions are not attack or vulnerability labels.",
            "File hashes are identity checks, not authenticity or complete loaded-code attestation.",
            "Keep both conditions and all correlated windows within one evaluation partition.",
        ],
    }
    return {**packet, "packet_binding_sha256": _binding(packet)}


def validate_analyst_decision(pair_dir: str | Path, decision: dict[str, Any]) -> dict[str, Any]:
    """Validate an external assertion; never claim reviewer identity is authenticated."""
    keys = {"schema_version", "packet_binding_sha256", "reviewer_id", "reviewed_at", "independence_declared", "decision", "rationale", "checks"}
    if not isinstance(decision, dict) or set(decision) != keys or decision["schema_version"] != "benign-pair-analyst-decision-v1":
        raise ValueError("invalid decision fields")
    packet = prepare_pair_review(pair_dir)
    if decision["packet_binding_sha256"] != packet["packet_binding_sha256"]:
        raise ValueError("decision is bound to stale or different evidence")
    for name in ("reviewer_id", "rationale"):
        if not isinstance(decision[name], str) or not decision[name].strip():
            raise ValueError(f"{name} must be supplied by the reviewer")
    parse_time(decision["reviewed_at"])
    if decision["independence_declared"] is not True:
        raise ValueError("independent reviewer declaration required")
    if decision["decision"] not in {"approved", "rejected", "inconclusive"}:
        raise ValueError("unsupported analyst decision")
    checks = decision["checks"]
    if not isinstance(checks, dict) or set(checks) != set(REVIEW_CHECKS) or any(type(value) is not bool for value in checks.values()):
        raise ValueError("all review checks must be explicit booleans")
    if decision["decision"] == "approved" and (not all(checks.values()) or not packet["collection_control_valid"]):
        raise ValueError("approval requires all review checks and valid collection/control evidence")
    return {
        "schema_version": "benign-pair-decision-validation-v1", "decision": decision["decision"],
        "packet_binding_sha256": packet["packet_binding_sha256"], "reviewer_id": decision["reviewer_id"],
        "decision_structure_valid": True, "reviewer_identity_authenticated": False,
        "independence_verified": False, "acquisition_labels_modified": False,
        "model_approved": False, "actionable": False,
    }