#!/usr/bin/env python3
"""Read-only recovery of sanitized historical log metadata; never replay NAS inputs."""

import argparse
import json
import shlex
import subprocess
from pathlib import Path


REMOTE = r'''
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

def timestamp_ns(value):
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})", value)
    if match is None:
        raise ValueError("unsupported timestamp")
    base = datetime.fromisoformat(match[1] + match[3].replace("Z", "+00:00"))
    return int(base.timestamp()) * 1000000000 + int((match[2] or "").ljust(9, "0"))

def extract(payload, start, end):
    rows = []
    counts = Counter()
    unparsed_timestamps = 0
    for number, line in enumerate(payload.decode("utf-8", errors="strict").splitlines(), 1):
        fields = dict(re.findall(r'(\w+)="([^"\n]*)"', line))
        if "time" not in fields:
            continue
        try:
            instant = timestamp_ns(fields["time"])
        except ValueError:
            unparsed_timestamps += 1
            continue
        if not start - 15000000000 <= instant <= end + 15000000000:
            continue
        phase = "during" if start <= instant <= end else ("before" if instant < start else "after")
        category = fields.get("CAT", "unknown")
        nf = fields.get("NF", "unknown")
        safe_nfs = {"AMF", "SMF", "UPF", "NRF", "AUSF", "UDM", "UDR", "NSSF", "PCF"}
        safe_categories = {"GIN", "PFCP", "Gmm", "Ngap", "NGAP", "SCTP", "NFM", "Consumer", "Producer", "Context"}
        row = {"event_time": fields["time"], "event_time_ns": instant, "phase": phase,
               "source_line": number, "nf_type": nf if nf in safe_nfs else "other",
               "category": category if category in safe_categories else "other"}
        message = fields.get("msg", "")
        if category == "GIN":
            access = re.match(r'^\|\s*(\d{3})\s*\|\s*[^|]*\|\s*(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*\|', message)
            if access:
                row.update(source="sbi", http_status=int(access[1]), http_method=access[2])
            else:
                row["source"] = "sbi_unparsed"
        elif category == "PFCP":
            row["source"] = "pfcp"
            row["direction"] = "request" if "Request" in message else ("response" if "Response" in message else "unknown")
        else:
            row["source"] = "free5gc"
        markers = {
            "registration_reject": r"(?i)registration reject|registrationreject|send.*reg.*reject",
            "authentication_subscription": r"(?i)authentication.?subscription|authentication-subscription",
            "sctp_shutdown": r"(?i)sctp.*shutdown|shutdown.*sctp",
            "ran_context_removal": r"(?i)remove.*ran|ran.*remov",
            "release_command": r"(?i)UE.?Context.?Release.?Command",
            "release_complete": r"(?i)UE.?Context.?Release.?Complete",
            "ng_setup": r"(?i)NG.?Setup",
        }
        row["observation_markers"] = [name for name, pattern in markers.items() if re.search(pattern, message)]
        counts[phase + "/" + row["source"]] += 1
        rows.append(row)
    return rows, dict(counts), unparsed_timestamps

if __name__ == "__main__":
    path = Path.home() / "free5gc/log/20261002_200341/free5gc.log"
    initial = path.stat()
    if path.is_symlink() or initial.st_size > 8388608:
        raise ValueError("unsafe or oversized source log")
    payload = path.read_bytes()
    final = path.stat()
    if (initial.st_ino, initial.st_size, initial.st_mtime_ns) != (final.st_ino, final.st_size, final.st_mtime_ns):
        raise ValueError("source changed during recovery")
    start_text = "2026-10-02T20:58:34.634928027+08:00"
    end_text = "2026-10-02T20:58:41.040804795+08:00"
    rows, counts, malformed = extract(payload, timestamp_ns(start_text), timestamp_ns(end_text))
    print(json.dumps({
        "schema_version": "retrospective-nas-log-recovery-v1", "run_id": "RNAS0001",
        "input_sha256": "49532803b6dd390d756842cf17aa830f0117e2262ec26f85e333d1c097e1b53a",
        "window_start": start_text, "window_end": end_text,
        "recovered_at": datetime.now(timezone.utc).isoformat(),
        "source_log": "~/free5gc/log/20261002_200341/free5gc.log",
        "source_log_sha256": hashlib.sha256(payload).hexdigest(), "source_size_bytes": len(payload),
        "source_unchanged_during_read": True, "counts": counts, "events": rows,
        "unparsed_timestamp_line_count": malformed, "linux_samples": None,
        "collection_mode": "retrospective_log_extraction", "collector_health_at_execution": "unknown",
        "monotonic_clock_evidence": None, "causal_attribution": "not_established",
        "telemetry_window_ready": False, "model_training_ready": False,
        "limitations": ["Log events are shared-host observations, not exclusive attribution to the test UE.",
                        "No historical collector health, kernel/packet completeness or Linux samples are reconstructed.",
                        "Regex markers are observations to review, not proof of successful release or causality."],
    }, sort_keys=True))
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite recovery evidence")
    command = ["ssh", "-p", "2222", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
               "-o", "StrictHostKeyChecking=yes", "-i", str(Path.home() / ".ssh/id_ecdsa"),
               "haochenqin-moss@127.0.0.1", "python3 -c " + shlex.quote(REMOTE)]
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
    report = json.loads(result.stdout)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({key: report[key] for key in ("run_id", "source_log_sha256", "counts", "telemetry_window_ready", "model_training_ready")}, indent=2))


if __name__ == "__main__":
    main()