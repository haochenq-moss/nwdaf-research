from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from nwdaf_research.input_testing.anomaly_dataset import FEATURES


def _nanoseconds(value: str) -> int:
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})", value)
    if match is None:
        raise ValueError("timezone-aware nanosecond timestamp required")
    base = datetime.fromisoformat(match[1] + match[3].replace("Z", "+00:00"))
    return int(base.timestamp()) * 1_000_000_000 + int((match[2] or "").ljust(9, "0"))


def build_partial_features(recovery_path: str | Path) -> dict[str, Any]:
    """Expose recoverable log statistics without constructing a valid model input."""
    payload = Path(recovery_path).read_bytes()
    recovery = json.loads(payload)
    if recovery.get("schema_version") != "retrospective-nas-log-recovery-v1" or recovery.get("collection_mode") != "retrospective_log_extraction":
        raise ValueError("retrospective recovery artifact required")
    start, end = _nanoseconds(recovery["window_start"]), _nanoseconds(recovery["window_end"])
    if end <= start:
        raise ValueError("invalid window")
    counts = Counter()
    during = []
    seen_lines = set()
    for row in recovery["events"]:
        instant = _nanoseconds(row["event_time"])
        if type(row["event_time_ns"]) is not int or row["event_time_ns"] != instant:
            raise ValueError("event timestamp identity mismatch")
        expected_phase = "during" if start <= instant <= end else ("before" if instant < start else "after")
        if row["phase"] != expected_phase or not start - 15_000_000_000 <= instant <= end + 15_000_000_000:
            raise ValueError("event phase/window mismatch")
        if type(row["source_line"]) is not int or row["source_line"] < 1 or row["source_line"] in seen_lines:
            raise ValueError("invalid or duplicate source line")
        seen_lines.add(row["source_line"])
        if row["source"] not in {"sbi", "sbi_unparsed", "pfcp", "free5gc"}:
            raise ValueError("unknown recovered source")
        counts[row["phase"] + "/" + row["source"]] += 1
        if expected_phase == "during":
            during.append(row)
    if dict(counts) != recovery["counts"]:
        raise ValueError("saved recovery counts disagree with events")
    sbi = [row for row in during if row["source"] == "sbi"]
    if any(type(row.get("http_status")) is not int or not 100 <= row["http_status"] <= 599 for row in sbi):
        raise ValueError("invalid recovered HTTP status")
    pfcp = [row for row in during if row["source"] == "pfcp"]
    values = dict.fromkeys(FEATURES, None)
    values.update({
        "duration_sec": (end - start) / 1_000_000_000,
        "sbi_event_count": len(sbi),
        "sbi_error_event_count": sum(row["http_status"] >= 400 for row in sbi),
        "pfcp_event_count": len(pfcp),
        "pfcp_request_count": sum(row.get("direction") == "request" for row in pfcp),
        "pfcp_response_count": sum(row.get("direction") == "response" for row in pfcp),
    })
    missing = [name for name in FEATURES if values[name] is None]
    return {
        "schema_version": "partial-retrospective-features-v1", "run_id": recovery["run_id"],
        "input_sha256": recovery["input_sha256"], "requested_contract": "linux-sbi-pfcp-v1",
        "feature_values": values, "available_field_count": len(FEATURES) - len(missing),
        "missing_field_count": len(missing), "missing_fields": missing,
        "recovery_artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "source_log_sha256": recovery["source_log_sha256"],
        "window_start": recovery["window_start"], "window_end": recovery["window_end"],
        "interval_semantics": "Historical inclusive log filter [start,end], not validated online counter window",
        "feature_provenance": {
            name: "Unavailable: no historical Linux samples or collector-health evidence" if value is None
            else ("Recorded UTC interval; no historical monotonic duration evidence" if name == "duration_sec"
                  else "Recomputed matching log records; no complete-traffic or healthy-collector guarantee")
            for name, value in values.items()
        },
        "training_ready": False, "status": "INCOMPLETE", "ground_truth_label": None,
        "imputation_performed": False, "inference_performed": False, "actionable": False,
        "limitations": [
            "No later live values, NRF runs or simulated samples are substituted.",
            "Zero PFCP records means no matches in this log interval, not verified absence of PFCP traffic.",
            "Availability flags cannot be inferred from file existence or successful retrospective reads.",
            "This record is not accepted by the health-bearing anomaly dataset loader.",
        ],
    }