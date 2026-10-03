from __future__ import annotations

import ctypes
import errno
import json
import math
import os
import re
import shlex
import shutil
import stat
import subprocess
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from nwdaf_research.live.heartbeat import HeartbeatReadinessGate
from nwdaf_research.live.ssh_observer import SSHLiveObserver
from nwdaf_research.live.telemetry_window import (
    BASELINE_CONTRACT, CollectorHealth, TelemetryWindow, parse_time,
)

SOURCES = ("linux", "sbi", "pfcp")
CLOCK_BASIS = "CLOCK_MONOTONIC_PROJECTED_UTC"
SOURCE_ID = "source-observation-poller-v1"
WARMUP_SEC = 30
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
EVENT_FIELDS = {
    "sbi": ("event_time", "collection_time", "nf_type", "procedure", "http_method", "status", "latency_ms"),
    "pfcp": ("event_time", "collection_time", "nf_type", "message_type", "direction", "level", "status", "latency_ms"),
}
COUNTERS = (
    "linux_event_count", "sbi_event_count", "sbi_error_event_count",
    "pfcp_event_count", "pfcp_request_count", "pfcp_response_count",
)
SOURCE_NOTES = {
    "linux": "Synchronous /proc/loadavg and /proc/meminfo observations.",
    "sbi": "Log-derived SBI from the newest timestamped run directory, not pcap; unmatched semantic lines cannot certify parser completeness.",
    "pfcp": "Log-derived PFCP from the newest timestamped run directory, not pcap; unmatched semantic lines cannot certify parser completeness.",
    "time": "Observation-time cursor reads; projected monotonic time, not physical UTC, packet time or causal subscriber actions.",
}

REMOTE_CODE = r'''
import contextlib
import hashlib
import ctypes
import datetime
import importlib
import json
import math
import os
import re
import signal
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
import uuid

SOURCES = ("linux", "sbi", "pfcp")
COUNTERS = ("linux_event_count", "sbi_event_count", "sbi_error_event_count",
            "pfcp_event_count", "pfcp_request_count", "pfcp_response_count")
EVENT_FIELDS = {
    "sbi": ("event_time", "collection_time", "nf_type", "procedure", "http_method", "status", "latency_ms"),
    "pfcp": ("event_time", "collection_time", "nf_type", "message_type", "direction", "level", "status", "latency_ms"),
}
MAX_POLL_BYTES = 2 * 1024 * 1024
MAX_LOG_BYTES = 512 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_EVENTS = 128
MAX_LOGS = 128
MAX_RUNTIME_NS = 89 * 1000000000

class CaptureDeadline(BaseException):
    pass

class Sink:
    def write(self, value):
        return len(value)
    def flush(self):
        pass

def projected(anchor, anchor_ns, timestamp_ns):
    return (anchor + datetime.timedelta(microseconds=(timestamp_ns - anchor_ns) // 1000)).isoformat()

def sanitized_event(source, event, timestamp):
    clean = {"event_time": timestamp, "collection_time": timestamp}
    choices = {
        "nf_type": {"AMF", "SMF", "UPF", "NRF", "AUSF", "UDM", "UDR", "NSSF", "PCF", "CHF", "NEF", "NWDAF"},
        "http_method": {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"},
        "direction": {"request", "response"},
        "level": {"TRACE", "DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL", "PANIC"},
        "procedure": {"registration", "deregistration", "authentication", "discovery", "subscription", "notification", "session_establishment", "session_modification", "session_release", "NFRegister", "NFUpdate", "NFDeregister", "NFDiscovery"},
        "message_type": {"Heartbeat Request", "Heartbeat Response", "Association Setup Request", "Association Setup Response", "Association Update Request", "Association Update Response", "Association Release Request", "Association Release Response", "Session Establishment Request", "Session Establishment Response", "Session Modification Request", "Session Modification Response", "Session Deletion Request", "Session Deletion Response", "Session Report Request", "Session Report Response", "Version Not Supported Response"},
    }
    for field in EVENT_FIELDS[source]:
        value = event.get(field)
        if field in choices and isinstance(value, str) and value in choices[field]:
            clean[field] = value
        elif field == "status":
            if type(value) is int and 100 <= value <= 599:
                clean[field] = value
            elif isinstance(value, str) and value in {"success", "error", "failed", "accepted", "rejected"}:
                clean[field] = value
        elif field == "latency_ms" and type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 3600000:
            clean[field] = value
    return clean

def open_log(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("not_regular")
        return descriptor, info
    except Exception:
        os.close(descriptor)
        raise

def birth_time_ns(descriptor):
    try:
        buffer = ctypes.create_string_buffer(256)
        function = ctypes.CDLL(None, use_errno=True).statx
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p]
        function.restype = ctypes.c_int
        if function(descriptor, b"", 0x1100, 0x800, ctypes.byref(buffer)) != 0:
            return None
        if not struct.unpack_from("=I", buffer.raw, 0)[0] & 0x800:
            return None
        seconds, nanoseconds = struct.unpack_from("=qI", buffer.raw, 80)
        return seconds * 1000000000 + nanoseconds
    except Exception:
        return None

class CursorPoller:
    def __init__(self, root, parsers, started_wall_ns):
        self.root = root
        self.parsers = parsers
        self.started_wall_ns = started_wall_ns
        self.cursors = {}
        self.initial_errors = []
        self.counts = dict.fromkeys(COUNTERS, 0)
        try:
            paths = self.paths()
            if not paths:
                raise ValueError("logs_absent")
            for path in paths:
                descriptor, info = open_log(path)
                try:
                    discard = False
                    if info.st_size:
                        os.lseek(descriptor, info.st_size - 1, os.SEEK_SET)
                        discard = os.read(descriptor, 1) != b"\n"
                    self.cursors[path] = {"inode": (info.st_dev, info.st_ino), "offset": info.st_size,
                                          "partial": b"", "discard": discard}
                finally:
                    os.close(descriptor)
        except Exception:
            self.initial_errors.append("log_baseline_failed")

    def paths(self):
        if not os.path.isdir(self.root) or os.path.islink(self.root):
            raise ValueError("log_directory_unavailable")
        directories = [self.root]
        paths = []
        entries = 0
        visited = 0
        while directories:
            visited += 1
            if visited > 128:
                raise ValueError("directory_inventory_cap")
            directory = directories.pop()
            with os.scandir(directory) as listing:
                for entry in listing:
                    entries += 1
                    if entries > 4096:
                        raise ValueError("entry_inventory_cap")
                    if entry.is_symlink():
                        raise ValueError("log_symlink")
                    if entry.is_dir(follow_symlinks=False):
                        directories.append(entry.path)
                    elif entry.name.endswith(".log"):
                        paths.append(entry.path)
                        if len(paths) > MAX_LOGS:
                            raise ValueError("log_inventory_cap")
        return sorted(paths)

    def poll(self):
        failures = {source: [] for source in SOURCES}
        events = {"sbi": [], "pfcp": []}
        linux = {}
        self.counts["linux_event_count"] += 1
        try:
            with open("/proc/loadavg", "r") as stream:
                load = float(stream.read(4096).split()[0])
            with open("/proc/meminfo", "r") as stream:
                memory = {}
                for line in stream.read(65536).splitlines():
                    key, value = line.split(":", 1)
                    if key in ("MemTotal", "MemAvailable"):
                        memory[key] = int(value.split()[0]) * 1024
            linux = {"load_1m": load, "memory_total": memory["MemTotal"], "memory_available": memory["MemAvailable"]}
            if not math.isfinite(load) or load < 0 or not 0 <= linux["memory_available"] <= linux["memory_total"] or linux["memory_total"] <= 0:
                raise ValueError("linux_metrics")
        except Exception:
            linux = {}
            failures["linux"].append("linux_read_failed")
        log_errors = list(self.initial_errors)
        remaining = MAX_POLL_BYTES
        try:
            paths = self.paths()
            if not paths or set(self.cursors) - set(paths):
                log_errors.append("known_log_missing")
            for path in paths:
                descriptor = None
                try:
                    descriptor, info = open_log(path)
                    cursor = self.cursors.get(path)
                    if cursor is None:
                        creation_ns = birth_time_ns(descriptor)
                        if creation_ns is None or creation_ns < self.started_wall_ns or info.st_mtime_ns < self.started_wall_ns:
                            log_errors.append("new_log_history_risk")
                            cursor = {"inode": (info.st_dev, info.st_ino), "offset": info.st_size, "partial": b"", "discard": True}
                        else:
                            cursor = {"inode": (info.st_dev, info.st_ino), "offset": 0, "partial": b"", "discard": False}
                        self.cursors[path] = cursor
                    if cursor["inode"] != (info.st_dev, info.st_ino) or info.st_size < cursor["offset"]:
                        log_errors.append("log_replaced_or_truncated")
                        continue
                    os.lseek(descriptor, cursor["offset"], os.SEEK_SET)
                    budget = min(MAX_LOG_BYTES, remaining)
                    if budget == 0:
                        log_errors.append("log_read_cap_exhausted")
                        continue
                    data = os.read(descriptor, budget)
                    remaining -= len(data)
                    cursor["offset"] += len(data)
                    after = os.fstat(descriptor)
                    current = os.stat(path, follow_symlinks=False)
                    if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != cursor["inode"]:
                        log_errors.append("log_changed_during_read")
                    if after.st_size > cursor["offset"] or len(data) == budget:
                        log_errors.append("log_read_cap_exhausted")
                    if after.st_size < cursor["offset"] or after.st_ino != info.st_ino:
                        log_errors.append("log_changed_during_read")
                    if cursor["discard"]:
                        newline = data.find(b"\n")
                        if newline == -1:
                            continue
                        data = data[newline + 1:]
                        cursor["discard"] = False
                    buffer = cursor["partial"] + data
                    lines = buffer.split(b"\n")
                    cursor["partial"] = lines.pop()
                    if len(cursor["partial"]) > MAX_LINE_BYTES:
                        cursor["partial"] = b""
                        log_errors.append("partial_line_cap_exhausted")
                    for raw in lines:
                        if len(raw) > MAX_LINE_BYTES:
                            log_errors.append("line_cap_exhausted")
                            continue
                        try:
                            line = raw.decode("utf-8", errors="strict")
                        except UnicodeError:
                            log_errors.append("log_decode_failed")
                            continue
                        for source in ("sbi", "pfcp"):
                            try:
                                parsed = self.parsers[source](line)
                                if parsed is None:
                                    continue
                                if not isinstance(parsed, dict):
                                    raise ValueError("parser_result")
                                self.counts[source + "_event_count"] += 1
                                if source == "sbi":
                                    status_code = parsed.get("status")
                                    if (type(status_code) is int and status_code >= 400) or parsed.get("level") in ("ERROR", "FATAL", "PANIC") or status_code in ("error", "failed"):
                                        self.counts["sbi_error_event_count"] += 1
                                else:
                                    direction = parsed.get("direction")
                                    if direction in ("request", "response"):
                                        self.counts["pfcp_" + direction + "_count"] += 1
                                if len(events[source]) >= MAX_EVENTS:
                                    failures[source].append("event_evidence_cap_exhausted")
                                else:
                                    events[source].append(sanitized_event(source, parsed, ""))
                            except Exception:
                                failures[source].append("parser_failed")
                except Exception:
                    log_errors.append("log_read_failed")
                finally:
                    if descriptor is not None:
                        os.close(descriptor)
        except Exception:
            log_errors.append("log_inventory_failed")
        for source in ("sbi", "pfcp"):
            failures[source].extend(log_errors)
        return linux, events, {source: sorted(set(errors)) for source, errors in failures.items()}

def select_log_root(root):
    candidates = []
    with os.scandir(root) as entries:
        for entry in entries:
            if re.fullmatch(r"[0-9]{8}_[0-9]{6}", entry.name) and entry.is_dir(follow_symlinks=False):
                path = os.path.join(entry.path, "free5gc.log")
                if os.path.isfile(path) and not os.path.islink(path):
                    candidates.append((entry.name, entry.path))
    if not candidates:
        raise ValueError("no_timestamped_log_run")
    return max(candidates)[1]

def parser_digest(path):
    descriptor, info = open_log(path)
    try:
        if info.st_size > 262144:
            raise ValueError("parser_size_limit")
        data = os.read(descriptor, 262145)
        after = os.fstat(descriptor)
        if len(data) != info.st_size or info.st_size != after.st_size or info.st_mtime_ns != after.st_mtime_ns:
            raise ValueError("parser_changed_during_hash")
        return hashlib.sha256(data).hexdigest()
    finally:
        os.close(descriptor)

def capture(window_count, duration_sec):
    started_wall_ns = time.time_ns()
    anchor_ns = time.monotonic_ns()
    anchor = datetime.datetime.now(datetime.timezone.utc)
    hostname = socket.gethostname()
    with open("/proc/sys/kernel/random/boot_id", "r") as stream:
        boot_id = stream.read(128).strip()
    instance = str(uuid.uuid4())
    domain = hostname + "/" + boot_id + "/CLOCK_MONOTONIC"
    root = os.path.expanduser("~/free5gc")
    sys.path[:0] = [root, os.path.expanduser("~")]
    parsers = {}
    paths = {}
    parser_hashes = {}
    startup_errors = []
    for source, name in (("sbi", "SBICollector"), ("pfcp", "PFCPCollector")):
        try:
            parser_path = os.path.join(root, "research", "collectors", source + ".py")
            digest = parser_digest(parser_path)
            module = importlib.import_module("research.collectors." + source)
            if os.path.realpath(module.__file__) != os.path.realpath(parser_path) or parser_digest(parser_path) != digest:
                raise ValueError("parser_import_provenance_mismatch")
            parser_hashes[source] = digest
            collector = getattr(module, name)
            parser = object.__new__(collector)
            parser.run_id = instance
            method = parser._parse_line
            parsers[source] = lambda line, method=method: method(line, "passive-cursor-log")
            paths[source] = "research/collectors/" + source + ".py"
        except Exception:
            startup_errors.append("parser_import_failed:" + source)
            def unavailable(line):
                raise ValueError("parser_unavailable")
            parsers[source] = unavailable
            paths[source] = "research/collectors/" + source + ".py"
    try:
        revision = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
            raise ValueError("revision")
    except Exception:
        revision = "unavailable"
        startup_errors.append("git_revision_unavailable")
    log_root = select_log_root(os.path.join(root, "log"))
    poller = CursorPoller(log_root, parsers, started_wall_ns)
    snapshots = []
    capture_errors = list(startup_errors)
    waiter = threading.Event()
    benign_state = None
    if globals().get("BENIGN_CONDITION", "passive") == "benign_nrf":
        benign_state = benign_initialize(window_count, duration_sec, NF_INSTANCE_ID)
    schedule_ns = None
    for index in range(31 + window_count * duration_sec):
        if schedule_ns is not None:
            deadline = schedule_ns + index * 1000000000
            wait_sec = max(0.0, (deadline - time.monotonic_ns()) / 1000000000)
            waiter.wait(min(wait_sec, max(0.0, (anchor_ns + MAX_RUNTIME_NS - time.monotonic_ns()) / 1000000000)))
        if time.monotonic_ns() - anchor_ns >= MAX_RUNTIME_NS:
            capture_errors.append("capture_duration_exhausted")
            break
        linux, events, failures = poller.poll()
        for source in ("sbi", "pfcp"):
            try:
                if parser_digest(os.path.join(root, paths[source])) != parser_hashes.get(source):
                    raise ValueError("parser_changed")
            except Exception:
                failures[source].append("parser_provenance_failed")
        timestamp_ns = time.monotonic_ns()
        if schedule_ns is None:
            schedule_ns = timestamp_ns
        timestamp = projected(anchor, anchor_ns, timestamp_ns)
        if timestamp_ns - anchor_ns >= MAX_RUNTIME_NS:
            capture_errors.append("capture_duration_exhausted")
            break
        health = {}
        heartbeats = {}
        for source in SOURCES:
            if "parser_import_failed:" + source in startup_errors:
                failures[source].append("parser_import_failed")
            healthy = not failures[source]
            health[source] = {"heartbeat_at": timestamp, "collector_healthy": healthy,
                              "telemetry_source_synced": healthy, "observed_through": timestamp}
            heartbeats[source] = {"source_id": "source-observation-poller-v1", "collector_instance_id": instance,
                "hostname": hostname, "boot_id": boot_id, "clock_domain": domain, "clock": "CLOCK_MONOTONIC",
                "timestamp_ns": timestamp_ns, "window_watermark_ns": timestamp_ns, "sequence_no": index,
                "status": "HEALTHY" if healthy else "FAILED",
                "metrics_summary": {"events_observed": poller.counts[source + "_event_count"], "drops": 0 if healthy else None}}
            for error in failures[source]:
                capture_errors.append(source + ":" + error)
        for source in ("sbi", "pfcp"):
            for event in events[source]:
                event["event_time"] = timestamp
                event["collection_time"] = timestamp
        snapshots.append({"type": "snapshot", "index": index, "monotonic_ns": timestamp_ns,
            "observed_at": timestamp, "linux_sample": linux, "counters": dict(poller.counts),
            "collectors": health, "heartbeats": heartbeats, "events": events,
            "poll_errors": failures})
        if benign_state is not None:
            benign_after_sample(benign_state, snapshots, capture_errors)
    result = {"schema": "passive-campaign-v1", "contract": "linux-sbi-pfcp-v1",
        "clock_basis": "CLOCK_MONOTONIC_PROJECTED_UTC", "anchor_monotonic_ns": anchor_ns,
        "anchor_projected_utc": anchor.isoformat(), "hostname": hostname, "boot_id": boot_id,
        "clock_domain": domain, "collector_instance_id": instance, "git_revision": revision,
        "parser_paths": paths, "parser_sha256": parser_hashes,
        "warmup_sec": 30, "duration_sec": duration_sec, "window_count": window_count,
        "read_budget": {"source_poll_bytes": MAX_POLL_BYTES, "per_log_bytes": MAX_LOG_BYTES, "aggregate_poll_bytes": MAX_POLL_BYTES},
        "capture_errors": sorted(set(capture_errors)), "snapshots": snapshots}
    if benign_state is not None:
        result.update(condition="benign_nrf", operation_receipt=benign_finish(benign_state))
    return result

def bounded_capture(window_count, duration_sec):
    def expired(signum, frame):
        raise CaptureDeadline()
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 88.0)
    try:
        return capture(window_count, duration_sec)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)

def main():
    window_count, duration_sec = map(int, sys.argv[1:])
    if not 1 <= window_count <= 3 or not 2 <= duration_sec <= 10:
        raise ValueError("invalid_bounds")
    with contextlib.redirect_stdout(Sink()), contextlib.redirect_stderr(Sink()):
        result = bounded_capture(window_count, duration_sec)
    sys.stdout.write(json.dumps(result, allow_nan=False, separators=(",", ":")))

if __name__ == "__main__":
    try:
        main()
    except CaptureDeadline:
        sys.stdout.write(json.dumps({"acquisition_error_type": "CaptureDeadline"}))
    except Exception as error:
        sys.stdout.write(json.dumps({"acquisition_error_type": type(error).__name__}))
'''


class CaptureError(ValueError):
    """Bounded acquisition/validation errors without remote payload or stderr."""


def _bounds(window_count: int, duration_sec: int) -> None:
    if type(window_count) is not int or not 1 <= window_count <= 3:
        raise ValueError("window_count must be an integer from 1 to 3")
    if type(duration_sec) is not int or not 2 <= duration_sec <= 10:
        raise ValueError("duration_sec must be an integer from 2 to 10")


def _condition(condition: str, registered_nf_instance_id: str | None, window_count: int, duration_sec: int,
               execute_benign: bool = False) -> str:
    if condition == "passive" and registered_nf_instance_id is None:
        return REMOTE_CODE
    if condition != "benign_nrf" or (window_count, duration_sec) != (3, 10):
        raise ValueError("invalid condition or benign collection bounds")
    if execute_benign is not True:
        raise ValueError("explicit execute_benign=True authorization required")
    from nwdaf_research.live.benign_control import remote_prefix

    return remote_prefix(registered_nf_instance_id) + REMOTE_CODE


def _exact_keys(row: Any, keys: set[str]) -> None:
    if not isinstance(row, dict) or set(row) != keys:
        raise CaptureError("invalid capture fields")


def _integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def _errors(value: Any) -> None:
    if not isinstance(value, list) or len(value) > 256 or any(
        not isinstance(item, str) or not re.fullmatch(r"[a-z_]{1,64}(?::[a-z_]{1,64})?", item)
        for item in value
    ):
        raise CaptureError("invalid capture error codes")


def validate_capture(capture: Any, *, window_count: int, duration_sec: int) -> dict[str, Any]:
    _bounds(window_count, duration_sec)
    keys = {
        "schema", "contract", "clock_basis", "anchor_monotonic_ns", "anchor_projected_utc",
        "hostname", "boot_id", "clock_domain", "collector_instance_id", "git_revision", "parser_paths",
        "warmup_sec", "duration_sec", "window_count", "read_budget", "capture_errors", "snapshots",
    }
    if isinstance(capture, dict) and "parser_sha256" in capture:
        keys.add("parser_sha256")
        hashes = capture["parser_sha256"]
        if not isinstance(hashes, dict) or not set(hashes) <= {"sbi", "pfcp"} or any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()
        ):
            raise CaptureError("invalid parser hashes")
        if set(hashes) != {"sbi", "pfcp"} and not capture.get("capture_errors"):
            raise CaptureError("missing parser hashes without failure evidence")
    if isinstance(capture, dict) and ("condition" in capture or "operation_receipt" in capture):
        from nwdaf_research.live.benign_control import validate_receipt

        keys.update({"condition", "operation_receipt"})
        if capture.get("condition") != "benign_nrf" or (window_count, duration_sec) != (3, 10):
            raise CaptureError("invalid capture condition")
        try:
            validate_receipt(capture.get("operation_receipt"))
        except (ValueError, TypeError):
            raise CaptureError("invalid sanitized operation receipt") from None
    _exact_keys(capture, keys)
    if (capture["schema"] != "passive-campaign-v1" or capture["contract"] != BASELINE_CONTRACT
            or capture["clock_basis"] != CLOCK_BASIS or capture["warmup_sec"] != 30
            or type(capture["warmup_sec"]) is not int
            or capture["window_count"] != window_count or type(capture["window_count"]) is not int
            or capture["duration_sec"] != duration_sec or type(capture["duration_sec"]) is not int):
        raise CaptureError("capture contract mismatch")
    if not isinstance(capture["hostname"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,253}", capture["hostname"]):
        raise CaptureError("invalid host metadata")
    for name in ("boot_id", "collector_instance_id"):
        if not isinstance(capture[name], str) or str(uuid.UUID(capture[name])) != capture[name]:
            raise CaptureError("invalid identity metadata")
    domain = f'{capture["hostname"]}/{capture["boot_id"]}/CLOCK_MONOTONIC'
    if capture["clock_domain"] != domain:
        raise CaptureError("invalid clock domain")
    if not isinstance(capture["git_revision"], str) or not re.fullmatch(r"[0-9a-f]{40,64}|unavailable", capture["git_revision"]):
        raise CaptureError("invalid revision metadata")
    if capture["parser_paths"] != {source: f"research/collectors/{source}.py" for source in ("sbi", "pfcp")}:
        raise CaptureError("invalid parser provenance")
    _exact_keys(capture["read_budget"], {"source_poll_bytes", "per_log_bytes", "aggregate_poll_bytes"})
    for name, maximum in (("source_poll_bytes", 2 * 1024 * 1024), ("per_log_bytes", 2 * 1024 * 1024), ("aggregate_poll_bytes", 4 * 1024 * 1024)):
        value = capture["read_budget"][name]
        if not _integer(value) or not 0 < value <= maximum:
            raise CaptureError("invalid read budget")
    _errors(capture["capture_errors"])
    anchor_ns = capture["anchor_monotonic_ns"]
    if not _integer(anchor_ns):
        raise CaptureError("invalid monotonic anchor")
    anchor = parse_time(capture["anchor_projected_utc"])
    if anchor.utcoffset() != timedelta(0):
        raise CaptureError("projection anchor must use UTC offset")
    snapshots = capture["snapshots"]
    expected_count = 31 + window_count * duration_sec
    if not isinstance(snapshots, list) or not 1 <= len(snapshots) <= expected_count:
        raise CaptureError("invalid snapshot count")
    if len(snapshots) != expected_count and "capture_duration_exhausted" not in capture["capture_errors"]:
        raise CaptureError("incomplete capture without bounded-stop evidence")
    previous_ns = anchor_ns - 1
    previous_projected = None
    for index, snapshot in enumerate(snapshots):
        _exact_keys(snapshot, {"type", "index", "monotonic_ns", "observed_at", "linux_sample", "counters", "collectors", "heartbeats", "events", "poll_errors"})
        timestamp_ns = snapshot["monotonic_ns"]
        if snapshot["type"] != "snapshot" or type(snapshot["index"]) is not int or snapshot["index"] != index:
            raise CaptureError("invalid snapshot index")
        if not _integer(timestamp_ns) or timestamp_ns <= previous_ns or not 0 <= timestamp_ns - anchor_ns < 89_000_000_000:
            raise CaptureError("invalid monotonic chronology")
        timestamp = parse_time(snapshot["observed_at"])
        if timestamp != anchor + timedelta(microseconds=(timestamp_ns - anchor_ns) // 1000):
            raise CaptureError("timestamp does not match monotonic projection")
        if previous_projected is not None and timestamp <= previous_projected:
            raise CaptureError("projected timestamps must strictly increase")
        previous_ns, previous_projected = timestamp_ns, timestamp
        _exact_keys(snapshot["counters"], set(COUNTERS))
        if any(not _integer(value) for value in snapshot["counters"].values()):
            raise CaptureError("invalid cumulative counters")
        linux = snapshot["linux_sample"]
        if linux != {}:
            _exact_keys(linux, {"load_1m", "memory_total", "memory_available"})
            if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in linux.values()):
                raise CaptureError("invalid Linux metrics")
            if not 0 <= linux["memory_available"] <= linux["memory_total"] or linux["memory_total"] <= 0:
                raise CaptureError("invalid Linux memory bounds")
        for name in ("collectors", "heartbeats", "poll_errors"):
            _exact_keys(snapshot[name], set(SOURCES))
        for source in SOURCES:
            health = snapshot["collectors"][source]
            _exact_keys(health, {"heartbeat_at", "collector_healthy", "telemetry_source_synced", "observed_through"})
            if any(type(health[name]) is not bool for name in ("collector_healthy", "telemetry_source_synced")):
                raise CaptureError("health flags must be booleans")
            if parse_time(health["heartbeat_at"]) != timestamp or parse_time(health["observed_through"]) != timestamp:
                raise CaptureError("invalid observation watermark")
            _errors(snapshot["poll_errors"][source])
            healthy = not snapshot["poll_errors"][source]
            if health["collector_healthy"] != healthy or health["telemetry_source_synced"] != healthy:
                raise CaptureError("poll health contradicts evidence")
            if source == "linux" and healthy and not linux:
                raise CaptureError("healthy Linux poll requires measurements")
            heartbeat = snapshot["heartbeats"][source]
            _exact_keys(heartbeat, {"source_id", "collector_instance_id", "hostname", "boot_id", "clock_domain", "clock", "timestamp_ns", "window_watermark_ns", "sequence_no", "status", "metrics_summary"})
            if any(heartbeat[name] != capture[name] for name in ("collector_instance_id", "hostname", "boot_id", "clock_domain")):
                raise CaptureError("heartbeat identity mismatch")
            if heartbeat["source_id"] != SOURCE_ID or heartbeat["clock"] != "CLOCK_MONOTONIC":
                raise CaptureError("invalid heartbeat source/clock")
            if any(not _integer(heartbeat[name]) for name in ("timestamp_ns", "window_watermark_ns", "sequence_no")):
                raise CaptureError("invalid heartbeat counters")
            if heartbeat["timestamp_ns"] != timestamp_ns or heartbeat["window_watermark_ns"] != timestamp_ns or heartbeat["sequence_no"] != index:
                raise CaptureError("invalid heartbeat poll boundary")
            _exact_keys(heartbeat["metrics_summary"], {"events_observed", "drops"})
            metrics = heartbeat["metrics_summary"]
            if not _integer(metrics["events_observed"]) or metrics["events_observed"] != snapshot["counters"][source + "_event_count"]:
                raise CaptureError("heartbeat totals contradict counters")
            valid_drops = type(metrics["drops"]) is int and metrics["drops"] == 0 if healthy else metrics["drops"] is None
            if heartbeat["status"] != ("HEALTHY" if healthy else "FAILED") or not valid_drops:
                raise CaptureError("invalid heartbeat health/drops")
        _exact_keys(snapshot["events"], {"sbi", "pfcp"})
        for source, events in snapshot["events"].items():
            if not isinstance(events, list) or len(events) > 128:
                raise CaptureError("invalid event evidence budget")
            for event in events:
                if not isinstance(event, dict) or set(event) - set(EVENT_FIELDS[source]):
                    raise CaptureError("event fields are not sanitized")
                if event.get("event_time") != snapshot["observed_at"] or event.get("collection_time") != snapshot["observed_at"]:
                    raise CaptureError("event observation time mismatch")
                _validate_event(source, event)
    return capture


def _validate_event(source: str, event: dict[str, Any]) -> None:
    namespace: dict[str, Any] = {"__name__": "passive_payload_validation"}
    if not hasattr(_validate_event, "sanitizer"):
        exec(compile(REMOTE_CODE, "<passive-poller>", "exec"), namespace)
        _validate_event.sanitizer = namespace["sanitized_event"]
    if _validate_event.sanitizer(source, event, event["collection_time"]) != event:
        raise CaptureError("event values are not sanitized")


def _health(snapshot: dict[str, Any]) -> dict[str, CollectorHealth]:
    return {source: CollectorHealth(
        heartbeat_at=parse_time(row["heartbeat_at"]), collector_healthy=row["collector_healthy"],
        telemetry_source_synced=row["telemetry_source_synced"], observed_through=parse_time(row["observed_through"]),
    ) for source, row in snapshot["collectors"].items()}


def process_capture(capture: dict[str, Any], *, window_count: int = 3, duration_sec: int = 10) -> dict[str, Any]:
    validate_capture(capture, window_count=window_count, duration_sec=duration_sec)
    snapshots = capture["snapshots"]
    gate = HeartbeatReadinessGate(capture["clock_domain"], contract=BASELINE_CONTRACT)
    counter_errors: set[str] = set()
    previous: dict[str, int] | None = None
    for snapshot in snapshots[:31]:
        for source in SOURCES:
            gate.observe(source, snapshot["heartbeats"][source], received_at_ns=snapshot["monotonic_ns"])
        counters = snapshot["counters"]
        if previous is not None:
            for name in COUNTERS:
                if counters[name] < previous[name]:
                    counter_errors.add("counter regression/reset: " + name)
            if counters["linux_event_count"] != previous["linux_event_count"] + 1:
                counter_errors.add("Linux poll counter mismatch")
        previous = counters
    warmup = gate.inspect(snapshots[min(30, len(snapshots) - 1)]["monotonic_ns"])
    blockers = list(warmup["errors"]) + sorted(counter_errors)
    if len(snapshots) < 31 or warmup["status"] != "READY":
        blockers.append("fixed 30-second warmup not ready")
    if capture["git_revision"] == "unavailable":
        blockers.append("git revision unavailable")
    if capture["capture_errors"]:
        blockers.extend(capture["capture_errors"])
    admitted = warmup["status"] == "READY" and not counter_errors and capture["git_revision"] != "unavailable"
    windows = []
    for offset in range(window_count):
        start_index = 30 + offset * duration_sec
        end_index = start_index + duration_sec
        rows = snapshots[start_index:end_index + 1]
        window_id = f"WBASE{offset + 1:03d}"
        complete = len(rows) == duration_sec + 1
        readiness: dict[str, Any] = {"contract": BASELINE_CONTRACT, "status": "COLLECTOR_UNAVAILABLE", "features": {}, "lifecycle": [], "collector_errors": list(blockers), "actionable": False, "sealed": False}
        stream = list(rows)
        actual_duration = None
        if admitted and complete:
            start = parse_time(rows[0]["observed_at"])
            end = parse_time(rows[-1]["observed_at"])
            actual_duration = (end - start).total_seconds()
            window = TelemetryWindow(start, duration_sec=actual_duration, heartbeat_timeout_sec=2, contract=BASELINE_CONTRACT)
            for row in rows:
                window.add_snapshot(row["observed_at"], counters=dict(row["counters"]), linux_sample=dict(row["linux_sample"]), collectors=_health(row))
                window.inspect(row["observed_at"])
            window.seal(end)
            readiness = window.inspect(end)
        elif complete:
            actual_duration = (parse_time(rows[-1]["observed_at"]) - parse_time(rows[0]["observed_at"])).total_seconds()
        if complete:
            stream.append({"type": "seal", "index": end_index, "monotonic_ns": rows[-1]["monotonic_ns"], "observed_at": rows[-1]["observed_at"], "admitted": admitted})
        metadata = {"window_id": window_id, "contract": BASELINE_CONTRACT, "clock_basis": CLOCK_BASIS,
            "start_index": start_index, "end_index": end_index, "nominal_duration_sec": duration_sec,
            "actual_duration_sec": actual_duration, "warmup_admitted": admitted, "capture_complete": complete,
            "declared_label": "normal/passive", "label_basis": "declared_by_protocol_not_validated",
            "start_monotonic_ns": rows[0]["monotonic_ns"] if rows else None,
            "end_monotonic_ns": rows[-1]["monotonic_ns"] if complete else None,
            "start_projected_at": rows[0]["observed_at"] if rows else None,
            "end_projected_at": rows[-1]["observed_at"] if complete else None}
        windows.append({"metadata": metadata, "readiness": readiness, "stream": stream})
    for window in windows:
        readiness = window["readiness"]
        for error in readiness.get("collector_errors", []) + readiness.get("evidence_errors", []):
            blockers.append(window["metadata"]["window_id"] + ": " + error)
    counts = dict(Counter(window["readiness"]["status"] for window in windows))
    if counts.get("READY") == window_count and not blockers:
        status = "READY"
    elif not admitted or "COLLECTOR_UNAVAILABLE" in counts or capture["capture_errors"]:
        status = "COLLECTOR_UNAVAILABLE"
    else:
        status = "INSUFFICIENT_EVIDENCE"
    report = {"contract": BASELINE_CONTRACT, "source_count": 3, "status": status,
        "window_status_counts": counts, "warmup": warmup, "blockers": sorted(set(blockers)),
        "inference_performed": False, "network_transmission_executed": False, "active_ue_not_modified": True,
        "operation_scope": "Read-only observer only; active UE not modified by this operation. Service continuity is not verified.",
        "clock_basis": CLOCK_BASIS, "source_notes": SOURCE_NOTES}
    processed = {"report": report, "windows": windows}
    if capture.get("condition") == "benign_nrf":
        from nwdaf_research.live.benign_control import extend_processed

        extend_processed(capture, processed)
    return processed


def acquire_capture(observer: SSHLiveObserver, *, window_count: int, duration_sec: int,
                    execute: Callable[..., Any] | None = None, condition: str = "passive",
                    registered_nf_instance_id: str | None = None, execute_benign: bool = False) -> dict[str, Any]:
    _bounds(window_count, duration_sec)
    remote_code = _condition(condition, registered_nf_instance_id, window_count, duration_sec, execute_benign)
    command = observer._ssh_command()[:-1]
    command = ["StrictHostKeyChecking=yes" if part.startswith("StrictHostKeyChecking=") else part for part in command]
    if observer.identity_file:
        command[command.index("-i") + 1] = os.path.expanduser(observer.identity_file)
    command.append("python3 -c " + shlex.quote(remote_code) + f" {window_count} {duration_sec}")
    try:
        result = (execute or subprocess.run)(command, check=True, capture_output=True, text=True,
            timeout=observer.timeout + WARMUP_SEC + window_count * duration_sec + 30)
        if not isinstance(result.stdout, str) or len(result.stdout.encode("utf-8")) > MAX_CAPTURE_BYTES:
            raise CaptureError("capture output exceeds bound")
        capture = json.loads(result.stdout)
        if isinstance(capture, dict) and set(capture) == {"acquisition_error_type"}:
            error_type = capture["acquisition_error_type"]
            known = {"CaptureDeadline", "ValueError", "OSError", "FileNotFoundError", "PermissionError", "RuntimeError", "ImportError", "ModuleNotFoundError"}
            raise CaptureError("remote acquisition failed: " + (error_type if isinstance(error_type, str) and error_type in known else "RemoteError"))
        capture = validate_capture(capture, window_count=window_count, duration_sec=duration_sec)
        if capture.get("condition", "passive") != condition:
            raise CaptureError("acquisition condition mismatch")
        return capture
    except CaptureError:
        raise
    except Exception as error:
        raise CaptureError("capture failed: " + type(error).__name__) from None


def _parent_descriptor(campaign_dir: str | Path) -> tuple[Path, int]:
    candidate = Path(campaign_dir).expanduser()
    home = Path.home()
    if not candidate.is_absolute() or ".." in candidate.parts or not candidate.is_relative_to(home) or candidate == home:
        raise ValueError("campaign directory must be a new absolute path beneath the user home")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in candidate.parent.parts[1:]:
            next_descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        try:
            os.stat(candidate.name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return candidate, descriptor
        raise FileExistsError("campaign directory already exists")
    except Exception:
        os.close(descriptor)
        raise


def _publish_exclusive(parent_fd: int, staging_name: str, destination: str) -> None:
    descriptors: list[int] = []
    created: list[tuple[int, str, tuple[int, int], bool]] = []

    def directory(parent: int, name: str) -> int:
        os.mkdir(name, mode=0o700, dir_fd=parent)
        descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        descriptors.append(descriptor)
        info = os.fstat(descriptor)
        created.append((parent, name, (info.st_dev, info.st_ino), True))
        return descriptor

    def link_tree(source: int, target: int) -> None:
        for name in sorted(os.listdir(source)):
            info = os.stat(name, dir_fd=source, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child_source = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=source)
                descriptors.append(child_source)
                link_tree(child_source, directory(target, name))
            elif stat.S_ISREG(info.st_mode):
                os.link(name, name, src_dir_fd=source, dst_dir_fd=target, follow_symlinks=False)
                created.append((target, name, (info.st_dev, info.st_ino), False))
            else:
                raise OSError("invalid staged artifact")
        os.fsync(target)

    try:
        target = directory(parent_fd, destination)
        source = os.open(staging_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        descriptors.append(source)
        link_tree(source, target)
    except Exception:
        for parent, name, identity, is_directory in reversed(created):
            try:
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if (info.st_dev, info.st_ino) == identity:
                    if is_directory:
                        os.rmdir(name, dir_fd=parent)
                    else:
                        os.unlink(name, dir_fd=parent)
            except OSError:
                pass
        raise
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    shutil.rmtree(Path(f"/proc/self/fd/{parent_fd}") / staging_name)


def _publish(parent_fd: int, staging_name: str, destination: str) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    rename = library.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(parent_fd, os.fsencode(staging_name), parent_fd, os.fsencode(destination), 1) != 0:
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError("campaign directory already exists")
        if code in (errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP):
            _publish_exclusive(parent_fd, staging_name, destination)
            return
        raise OSError(code, "atomic campaign publication failed")


def run_campaign(campaign_dir: str | Path, *, window_count: int = 3, duration_sec: int = 10,
                 observer: SSHLiveObserver | None = None, execute: Callable[..., Any] | None = None,
                 condition: str = "passive", registered_nf_instance_id: str | None = None,
                 execute_benign: bool = False) -> dict[str, Any]:
    _bounds(window_count, duration_sec)
    _condition(condition, registered_nf_instance_id, window_count, duration_sec, execute_benign)
    destination, parent_fd = _parent_descriptor(campaign_dir)
    staging_name = ".passive-campaign-" + uuid.uuid4().hex
    staging: Path | None = None
    try:
        capture = acquire_capture(observer or SSHLiveObserver(), window_count=window_count, duration_sec=duration_sec,
                                  execute=execute, condition=condition, registered_nf_instance_id=registered_nf_instance_id,
                                  execute_benign=execute_benign)
        processed = process_capture(capture, window_count=window_count, duration_sec=duration_sec)
        os.mkdir(staging_name, mode=0o700, dir_fd=parent_fd)
        staging = Path(f"/proc/self/fd/{parent_fd}") / staging_name
        manifest = {"schema": "passive-campaign-v1", "contract": BASELINE_CONTRACT, "source_count": 3,
            "hostname": capture["hostname"], "boot_id": capture["boot_id"], "git_revision": capture["git_revision"],
            "parser_paths": capture["parser_paths"], "clock_basis": CLOCK_BASIS, "clock_domain": capture["clock_domain"],
            "collector_instance_id": capture["collector_instance_id"], "anchor_monotonic_ns": capture["anchor_monotonic_ns"],
            "anchor_projected_utc": capture["anchor_projected_utc"], "warmup_sec": WARMUP_SEC,
            "window_count": window_count, "nominal_duration_sec": duration_sec, "read_budget": capture["read_budget"],
            "source_notes": SOURCE_NOTES, "collection_semantics": "observation_time_cursor_reads_excluding_preexisting_history",
            "network_transmission_executed": False, "transport": "single_read_only_ssh_acquisition",
            "network_transmission_scope": "No generated SBI/PFCP/test/subscriber traffic; SSH transport is used for acquisition.",
            "publication_policy": "atomic_noreplace_when_supported_else_exclusive_hardlinks_with_rollback",
            "inference_performed": False, "active_ue_not_modified": True}
        if "parser_sha256" in capture:
            manifest["parser_sha256"] = capture["parser_sha256"]
        if condition == "benign_nrf":
            report = processed["report"]
            manifest.update(condition=condition, operation_receipt=capture["operation_receipt"],
                control_valid=report["control_valid"], network_transmission_executed=report["network_transmission_executed"],
                generated_traffic_status=report["generated_traffic_status"],
                transport="single_ssh_acquisition_with_fixed_benign_nrf",
                network_transmission_scope=report["operation_scope"])
        documents = [(staging / "manifest.json", manifest), (staging / "capture.json", capture), (staging / "report.json", processed["report"])]
        (staging / "windows").mkdir(mode=0o700)
        for window in processed["windows"]:
            folder = staging / "windows" / window["metadata"]["window_id"]
            folder.mkdir(mode=0o700)
            documents.extend([(folder / "readiness.json", window["readiness"]), (folder / "metadata.json", window["metadata"])])
            with (folder / "snapshots.jsonl").open("x", encoding="utf-8") as stream:
                os.chmod(stream.name, 0o600)
                for row in window["stream"]:
                    stream.write(json.dumps(row, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        for path, document in documents:
            with path.open("x", encoding="utf-8") as stream:
                os.chmod(stream.name, 0o600)
                json.dump(document, stream, allow_nan=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        _publish(parent_fd, staging_name, destination.name)
        staging = None
        return {"status": processed["report"]["status"], "blockers": processed["report"]["blockers"],
            "window_status_counts": processed["report"]["window_status_counts"], "campaign_dir": str(destination),
            "manifest_path": str(destination / "manifest.json"), "report_path": str(destination / "report.json")}
    finally:
        if staging is not None:
            shutil.rmtree(staging)
        os.close(parent_fd)