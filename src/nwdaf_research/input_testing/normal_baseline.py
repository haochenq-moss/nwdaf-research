from __future__ import annotations

import json
import shlex
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from nwdaf_research.input_testing.records import RunLabel, read_jsonl, write_jsonl
from nwdaf_research.live.ssh_observer import SSHLiveObserver


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


REMOTE_BASELINE = r'''
import atexit
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from research.collectors.linux.system import LinuxCollector
from research.collectors.pfcp import PFCPCollector
from research.collectors.sbi import SBICollector

run_id = sys.argv[1]
duration = float(sys.argv[2])
capture_dir = Path(tempfile.mkdtemp(prefix="nwdaf-normal-run-"))
atexit.register(shutil.rmtree, capture_dir, ignore_errors=True)
log_root = Path.home() / "free5gc" / "log"

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
        "evidence": {"source": "remote_proc_snapshot", "collection": "single_read_only_host_sample"},
        "unavailable_features": ["process_event_count", "sbi_event_rate", "pfcp_message_rate", "service_latency", "ue_namespace_tunnel_count"],
    }

def read_events(source, allowed_fields):
    path = capture_dir / source / "events.jsonl"
    if not path.exists():
        return []
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        event = {key: raw[key] for key in allowed_fields if key in raw}
        event.update({"run_id": run_id, "source": source})
        result.append(event)
    return result

before_snapshot = host_snapshot()
linux = LinuxCollector(capture_dir / "linux" / "events.jsonl", run_id, interval_sec=0.25)
sbi = SBICollector(capture_dir / "sbi" / "events.jsonl", log_root, run_id)
pfcp = PFCPCollector(capture_dir / "pfcp" / "events.jsonl", log_root, run_id)
collectors = (linux, sbi, pfcp)
try:
    for collector in collectors:
        collector.start()
    started_at = utc_now()
    time.sleep(duration)
    finished_at = utc_now()
    after_snapshot = host_snapshot()
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
    "started_at": started_at,
    "finished_at": finished_at,
    "free5gc_commit": commit,
    "before_snapshot": before_snapshot,
    "after_snapshot": after_snapshot,
    "linux_events": read_events("linux", ("event_time", "collection_time", "host_id", "event_type", "cpu_count", "load_1m", "memory_bytes")),
    "sbi_events": read_events("sbi", ("event_time", "collection_time", "nf_type", "procedure", "http_method", "status", "latency_ms")),
    "pfcp_events": read_events("pfcp", ("event_time", "collection_time", "nf_type", "message_type", "direction", "level", "status", "latency_ms")),
}, sort_keys=True))
'''


def _next_run_number(campaign: Path) -> int:
    used: list[int] = []
    labels_path = campaign / "run_labels.jsonl"
    if labels_path.exists():
        for label in read_jsonl(labels_path, RunLabel):
            if label.run_id.startswith("RNORM") and label.run_id[5:].isdigit():
                used.append(int(label.run_id[5:]))
    runs_root = campaign / "runs"
    if runs_root.exists():
        for child in runs_root.glob("RNORM*"):
            if child.name[5:].isdigit():
                used.append(int(child.name[5:]))
    return max(used, default=0) + 1


def _ssh_command(observer: SSHLiveObserver, remote_command: str) -> list[str]:
    command = [
        "ssh", "-T", "-p", str(observer.port),
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={max(1, int(observer.timeout))}",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    if observer.identity_file:
        command.extend(["-i", observer.identity_file])
    command.extend([f"{observer.user}@{observer.host}", remote_command])
    return command


def capture_normal_baseline(
    *,
    campaign_dir: str | Path,
    split: str,
    duration_sec: float = 2.0,
    observer: SSHLiveObserver | None = None,
) -> dict[str, Any]:
    """Capture a passive no-request baseline run; no scenarios or traffic start."""
    if split not in {"train", "held_out"}:
        raise ValueError("split must be train or held_out")
    if not 1.0 <= duration_sec <= 10.0:
        raise ValueError("duration_sec must be between 1 and 10 seconds")
    campaign = Path(campaign_dir)
    labels_path = campaign / "run_labels.jsonl"
    labels = read_jsonl(labels_path, RunLabel) if labels_path.exists() else []
    run_id = f"RNORM{_next_run_number(campaign):03d}"
    if any(label.run_id == run_id for label in labels) or (campaign / "runs" / run_id).exists():
        raise FileExistsError(f"run ID already exists: {run_id}")

    ssh = observer or SSHLiveObserver()
    remote_code = REMOTE_BASELINE
    command = _ssh_command(
        ssh,
        'cd "$HOME/free5gc" && python3 -c ' + shlex.quote(remote_code)
        + " " + shlex.quote(run_id) + " " + shlex.quote(str(duration_sec)),
    )
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=ssh.timeout + duration_sec + 40,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr.strip() or "normal baseline collector failed")[-1200:])
    try:
        captured = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("normal baseline collector returned invalid JSON") from error

    run_dir = campaign / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    for phase, key in (("before", "before_snapshot"), ("after", "after_snapshot")):
        snapshot = captured[key]
        row = {"run_id": run_id, "input_id": None, "phase": phase, **snapshot}
        with (campaign / "live_observations.jsonl").open("a", encoding="utf-8", newline="\n") as destination:
            destination.write(json.dumps(row, sort_keys=True) + "\n")
    (run_dir / "live_observations.jsonl").write_text(
        "".join(json.dumps({"run_id": run_id, "input_id": None, "phase": phase, **captured[key]}, sort_keys=True) + "\n"
                  for phase, key in (("before", "before_snapshot"), ("after", "after_snapshot"))),
        encoding="utf-8",
    )

    for source in ("linux", "sbi", "pfcp"):
        events = captured.get(f"{source}_events", [])
        if events:
            event_path = run_dir / source / "events.jsonl"
            event_path.parent.mkdir(parents=True, exist_ok=True)
            event_path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8")

    start = captured["before_snapshot"]["observed_at"]
    end = captured["after_snapshot"]["observed_at"]
    duration = (datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()
    _write_json(run_dir / "metadata.json", {
        "run_id": run_id,
        "scenario_id": "PASSIVE_NORMAL_BASELINE",
        "load_profile": "uncontrolled_live_lab",
        "created_at": start,
        "duration_sec": duration,
        "host_id": captured["before_snapshot"]["host"],
        "status": "complete",
        "provenance": {"collector_version": "nwdaf-passive-baseline-v1", "free5gc_commit": captured["free5gc_commit"]},
        "telemetry_notes": {
            source: f"{len(captured.get(source + '_events', []))} normalized passive events"
            for source in ("linux", "sbi", "pfcp")
        },
    })
    _write_json(run_dir / "ground_truth.json", {
        "run_id": run_id, "scenario_id": "PASSIVE_NORMAL_BASELINE", "anomalous": False,
        "security": False, "class": "normal", "severity": "none",
        "attack_phase": "not_applicable", "service_impact": "none", "action": None,
    })
    _write_json(run_dir / "timeline.json", {
        "run_id": run_id,
        "timeline": {"T0": start, "T1": captured["started_at"], "T2": captured["finished_at"], "T3": captured["finished_at"], "T4": end},
    })
    labels.append(RunLabel(run_id, "normal", split))
    write_jsonl(labels_path, labels)
    return {
        "run_id": run_id,
        "label": "normal",
        "split": split,
        "duration_sec": duration,
        "event_counts": {source: len(captured.get(f"{source}_events", [])) for source in ("linux", "sbi", "pfcp")},
        "free5gc_commit": captured["free5gc_commit"],
    }