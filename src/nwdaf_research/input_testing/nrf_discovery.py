from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, TypeVar

from nwdaf_research.input_testing.live_capture import capture_live_observation
from nwdaf_research.input_testing.records import (
    InputCase,
    RunLabel,
    TestOutcome,
    read_jsonl,
    write_jsonl,
)
from nwdaf_research.input_testing.snapshot_runs import materialize_input_test_runs
from nwdaf_research.live.ssh_observer import SSHLiveObserver


REQUEST_TARGET = (
    "/nnrf-disc/v1/nf-instances?requester-nf-type=AMF"
    "&target-nf-type=AUSF&service-names=nausf-auth"
)
AUTH_CONTEXT = "OAuth2 client_credentials; nf_type=AMF; target_nf_type=NRF; scope=nnrf-disc"
REMOTE_PYTHON = r'''
import json
import atexit
import sys
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

from research.collectors.linux.system import LinuxCollector
from research.collectors.pfcp import PFCPCollector
from research.collectors.sbi import SBICollector

run_id = sys.argv[1]
registered = sys.argv[2]
capture_dir = Path(tempfile.mkdtemp(prefix="nwdaf-input-run-"))
atexit.register(shutil.rmtree, capture_dir, ignore_errors=True)
log_root = Path.home() / "free5gc" / "log"
linux = LinuxCollector(capture_dir / "linux" / "events.jsonl", run_id, interval_sec=0.25)
sbi = SBICollector(capture_dir / "sbi" / "events.jsonl", log_root, run_id)
pfcp = PFCPCollector(capture_dir / "pfcp" / "events.jsonl", log_root, run_id)
collectors = (linux, sbi, pfcp)

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def host_snapshot():
    try:
        load_1m = float(os.getloadavg()[0])
    except OSError:
        load_1m = 0.0
    memory = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw_value = line.split(":", 1)
            memory[key] = int(raw_value.strip().split()[0]) * 1024
    except (OSError, ValueError):
        pass
    total = float(memory.get("MemTotal", 0))
    available = float(memory.get("MemAvailable", 0))
    return {
        "observed_at": utc_now(),
        "host": socket.gethostname(),
        "features": {
            "linux_load_1m_mean": load_1m,
            "linux_load_1m_std": 0.0,
            "linux_load_1m_max": load_1m,
            "linux_load_1m_min": load_1m,
            "linux_memory_total_mean": total,
            "linux_memory_available_mean": available,
            "memory_available_ratio_mean": available / total if total else 0.0,
        },
        "evidence": {
            "source": "remote_proc_snapshot",
            "collection": "single_read_only_host_sample",
            "ssh_endpoint": "reverse_tunnel",
            "event_count_window": "single-host-sample",
        },
        "unavailable_features": [
            "process_event_count", "sbi_event_rate", "pfcp_message_rate",
            "service_latency", "ue_namespace_tunnel_count",
        ],
    }

def read_events(source, allowed_fields):
    path = capture_dir / source / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        event = {key: raw[key] for key in allowed_fields if key in raw}
        event.update({"run_id": run_id, "source": source})
        events.append(event)
    return events

before_snapshot = host_snapshot()
try:
    for collector in collectors:
        collector.start()
    started_at = utc_now()
    start_clock = time.perf_counter()
    token_request = urllib.request.Request(
        "http://127.0.0.10:8000/oauth2/token",
        data=urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "nfInstanceId": registered,
            "nfType": "AMF",
            "targetNfType": "NRF",
            "scope": "nnrf-disc",
        }).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(token_request, timeout=5) as response:
        token = json.loads(response.read())["access_token"]
    request = urllib.request.Request(
        "http://127.0.0.10:8000__REQUEST_TARGET__",
        headers={"Authorization": "Bearer " + token},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            http_status = response.status
            response.read()
    except urllib.error.HTTPError as error:
        http_status = error.code
        error.close()
    duration_ms = (time.perf_counter() - start_clock) * 1000
    finished_at = utc_now()
    after_snapshot = host_snapshot()
    del token
finally:
    for collector in collectors:
        collector.stop()
    for collector in (sbi, pfcp):
        with collector.output_path.open("a", encoding="utf-8") as stream:
            for log_path in collector.log_root.glob("**/*.log"):
                collector._read_new(log_path, stream)

commit = subprocess.run(
    ["git", "-C", str(Path.home() / "free5gc"), "rev-parse", "HEAD"],
    check=True, capture_output=True, text=True, timeout=5,
).stdout.strip()
print(json.dumps({
    "window_start": started_at,
    "window_end": finished_at,
    "http_status": http_status,
    "duration_ms": round(duration_ms, 3),
    "free5gc_commit": commit,
    "before_snapshot": before_snapshot,
    "after_snapshot": after_snapshot,
    "linux_events": read_events("linux", (
        "event_time", "collection_time", "host_id", "event_type", "cpu_count", "load_1m", "memory_bytes",
    )),
    "sbi_events": read_events("sbi", (
        "event_time", "collection_time", "nf_type", "procedure", "http_method", "status", "latency_ms",
    )),
    "pfcp_events": read_events("pfcp", (
        "event_time", "collection_time", "nf_type", "message_type", "direction", "level", "status", "latency_ms",
    )),
}, sort_keys=True))
'''


def validate_candidate_path(request_path: str) -> str:
    parsed = urllib.parse.urlsplit(request_path)
    if parsed.scheme or parsed.netloc or parsed.fragment or parsed.path != "/nnrf-disc/v1/nf-instances":
        raise ValueError("candidate must be a relative NRF discovery path")
    if not parsed.query:
        raise ValueError("candidate must include NRF discovery query parameters")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    allowed_keys = {"requester-nf-type", "target-nf-type", "service-names", "limit"}
    required_keys = {"requester-nf-type", "target-nf-type", "service-names"}
    if set(query) - allowed_keys or not required_keys <= set(query):
        raise ValueError("candidate has unsupported or missing query parameters")
    if any(len(values) != 1 for values in query.values()):
        raise ValueError("candidate query parameters must not be repeated")
    if query["requester-nf-type"][0] not in {"AMF", "AUSF", "UDM"}:
        raise ValueError("candidate requester NF is not allowlisted")
    if query["target-nf-type"][0] not in {"AUSF", "UDM", "UDR"}:
        raise ValueError("candidate target NF is not allowlisted")
    if query["service-names"][0] not in {"nausf-auth", "nudm-ueau", "nudr-dr"}:
        raise ValueError("candidate service is not allowlisted")
    if "limit" in query and query["limit"][0] not in {"1", "5"}:
        raise ValueError("candidate limit must be 1 or 5")
    return request_path


def _remote_python_source(request_path: str = REQUEST_TARGET) -> str:
    return REMOTE_PYTHON.replace("__REQUEST_TARGET__", request_path)


def _remote_probe(run_id: str, nf_instance_id: str, request_path: str = REQUEST_TARGET) -> str:
    return (
        'cd "$HOME/free5gc" && python3 -c '
        + shlex.quote(_remote_python_source(request_path))
        + " "
        + shlex.quote(run_id)
        + " "
        + shlex.quote(nf_instance_id)
    )

Record = TypeVar("Record", InputCase, TestOutcome, RunLabel)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _read_records(path: Path, record_type: type[Record]) -> list[Record]:
    return read_jsonl(path, record_type) if path.exists() else []


def _append_record(path: Path, record: Record, record_type: type[Record], key: str) -> None:
    records = _read_records(path, record_type)
    if any(getattr(existing, key) == getattr(record, key) for existing in records):
        raise ValueError(f"duplicate {key} in {path}: {getattr(record, key)}")
    write_jsonl(path, [*records, record])


def _ssh_probe(
    observer: SSHLiveObserver,
    run_id: str,
    nf_instance_id: str,
    request_path: str,
) -> dict[str, Any]:
    command = [
        "ssh",
        "-T",
        "-p",
        str(observer.port),
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={max(1, int(observer.timeout))}",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    if observer.identity_file:
        command.extend(["-i", observer.identity_file])
    command.extend([
        f"{observer.user}@{observer.host}",
        _remote_probe(run_id, nf_instance_id, request_path),
    ])
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=observer.timeout + 40,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "remote NRF probe failed"
        raise RuntimeError(detail[-1000:])
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("remote NRF probe returned invalid JSON") from error
    return result


def run_nrf_discovery_case(
    *,
    campaign_dir: str | Path,
    run_id: str,
    input_id: str,
    nf_instance_id: str,
    request_path: str = REQUEST_TARGET,
    input_source: str = "ordinary",
    generator_model: str | None = None,
    trial_group: str | None = None,
    replicate_index: int | None = None,
    template_choice: int | None = None,
    observer: SSHLiveObserver | None = None,
) -> dict[str, Any]:
    """Run one fixed read-only NRF discovery request and record its outcome.

    The OAuth token is acquired and consumed remotely, and is never returned or
    written. The request target is fixed in this module; arbitrary URLs and
    payloads cannot be supplied through this helper.
    """
    for field_name, value in (("run_id", run_id), ("input_id", input_id)):
        if not _SAFE_ID.fullmatch(value):
            raise ValueError(f"{field_name} contains unsupported characters")
    try:
        uuid.UUID(nf_instance_id)
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError("nf_instance_id must be a UUID for a registered NF") from error
    request_path = validate_candidate_path(request_path)
    if input_source not in {"ordinary", "llm_suggested"}:
        raise ValueError("input_source must be ordinary or llm_suggested")
    if input_source == "llm_suggested" and not generator_model:
        raise ValueError("LLM-suggested inputs require generator_model provenance")

    campaign = Path(campaign_dir)
    input_path = campaign / "input_cases.jsonl"
    outcome_path = campaign / "outcomes.jsonl"
    labels_path = campaign / "run_labels.jsonl"
    existing_cases = _read_records(input_path, InputCase)
    existing_outcomes = _read_records(outcome_path, TestOutcome)
    existing_labels = _read_records(labels_path, RunLabel)
    if any(case.input_id == input_id for case in existing_cases):
        raise ValueError(f"input_id already exists: {input_id}")
    if any(outcome.run_id == run_id for outcome in existing_outcomes):
        raise ValueError(f"run_id already has an outcome: {run_id}")
    if any(label.run_id == run_id for label in existing_labels):
        raise ValueError(f"run_id already has a label: {run_id}")
    if (campaign / "runs" / run_id).exists():
        raise FileExistsError(f"refusing to overwrite existing run directory: {campaign / 'runs' / run_id}")

    corpus_dir = "corpus/llm" if input_source == "llm_suggested" else "corpus/ordinary"
    corpus_path = Path(corpus_dir) / f"{input_id}.txt"
    corpus_file = campaign / corpus_path
    if corpus_file.exists():
        raise FileExistsError(f"refusing to overwrite input corpus file: {corpus_file}")

    snapshot_path = campaign / "live_observations.jsonl"
    observation_client = observer or SSHLiveObserver()
    remote_result = _ssh_probe(observation_client, run_id, nf_instance_id, request_path)
    snapshots = []
    for phase, key in (("before", "before_snapshot"), ("after", "after_snapshot")):
        snapshot = remote_result.get(key)
        if not isinstance(snapshot, dict):
            raise RuntimeError(f"remote probe omitted {phase} host snapshot")
        snapshots.append({
            "run_id": run_id,
            "input_id": input_id,
            "phase": phase,
            **snapshot,
        })
    with snapshot_path.open("a", encoding="utf-8", newline="\n") as destination:
        for row in snapshots:
            destination.write(json.dumps(row, sort_keys=True) + "\n")

    request_bytes = (request_path + "\n").encode("ascii")
    corpus_file.parent.mkdir(parents=True, exist_ok=True)
    corpus_file.write_bytes(request_bytes)
    http_status = int(remote_result["http_status"])
    if 200 <= http_status < 300:
        outcome_status = "accepted"
    elif 400 <= http_status < 500:
        outcome_status = "rejected"
    else:
        outcome_status = "error"

    case = InputCase(
        input_id=input_id,
        input_source=input_source,
        component="NRF Nnrf_NFDiscovery",
        input_sha256=hashlib.sha256(request_bytes).hexdigest(),
        corpus_path=corpus_path.as_posix(),
        free5gc_commit=str(remote_result["free5gc_commit"]),
        generator_model=generator_model,
        auth_context=AUTH_CONTEXT,
        trial_group=trial_group,
        replicate_index=replicate_index,
        template_choice=template_choice,
    )
    outcome = TestOutcome(
        outcome_id=f"{input_id}-outcome",
        input_id=input_id,
        run_id=run_id,
        window_start=str(remote_result["window_start"]),
        window_end=str(remote_result["window_end"]),
        status=outcome_status,
        http_status=http_status,
        duration_ms=float(remote_result["duration_ms"]),
    )
    label = RunLabel(run_id=run_id, label="input_test", split="train")
    _append_record(input_path, case, InputCase, "input_id")
    _append_record(outcome_path, outcome, TestOutcome, "outcome_id")
    _append_record(labels_path, label, RunLabel, "run_id")

    run_dir = materialize_input_test_runs(campaign, run_ids={run_id})[0]
    event_counts: dict[str, int] = {}
    for source in ("linux", "sbi", "pfcp"):
        events = remote_result.get(f"{source}_events", [])
        event_counts[source] = len(events)
        if not events:
            continue
        event_path = run_dir / source / "events.jsonl"
        event_path.parent.mkdir(parents=True, exist_ok=True)
        with event_path.open("a" if source == "linux" else "w", encoding="utf-8", newline="\n") as destination:
            for event in events:
                destination.write(json.dumps(event, sort_keys=True) + "\n")

    metadata_path = run_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    for source in ("linux", "sbi", "pfcp"):
        if event_counts[source]:
            metadata["telemetry_notes"][source] = (
                f"{event_counts[source]} normalized metadata events captured; "
                "raw payloads, addresses, and session identifiers excluded"
            )
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "run_id": run_id,
        "input_id": input_id,
        "input_source": case.input_source,
        "http_status": http_status,
        "outcome": outcome_status,
        "duration_ms": outcome.duration_ms,
        "free5gc_commit": case.free5gc_commit,
        "corpus_path": case.corpus_path,
        "request_sha256": case.input_sha256,
        "token_persisted": False,
        "event_counts": event_counts,
    }