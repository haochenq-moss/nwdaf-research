from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class TelemetryStatus(str, Enum):
    ACCUMULATING = "ACCUMULATING"
    COLLECTOR_UNAVAILABLE = "COLLECTOR_UNAVAILABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    READY = "READY"


COUNTER_SOURCES = {
    "linux_event_count": "linux",
    "process_event_count": "process",
    "sbi_event_count": "sbi",
    "sbi_error_event_count": "sbi",
    "pfcp_event_count": "pfcp",
    "pfcp_request_count": "pfcp",
    "pfcp_response_count": "pfcp",
    "free5gc_event_count": "free5gc",
    "ebpf_event_count": "ebpf",
}
AVAILABILITY_SOURCES = {
    "sbi_telemetry_available": "sbi",
    "pfcp_telemetry_available": "pfcp",
    "free5gc_telemetry_available": "free5gc",
    "ebpf_telemetry_available": "ebpf",
}
LINUX_FEATURES = (
    "linux_load_1m_mean", "linux_load_1m_std", "linux_load_1m_min", "linux_load_1m_max",
    "linux_memory_total_mean", "linux_memory_available_mean", "memory_available_ratio_mean",
)
WINDOW_FEATURES = ("duration_sec", *LINUX_FEATURES, *COUNTER_SOURCES, *AVAILABILITY_SOURCES)
FULL_CONTRACT = "full-six-source-v1"
BASELINE_CONTRACT = "linux-sbi-pfcp-v1"
CONTRACT_SOURCES = {
    FULL_CONTRACT: tuple(sorted(set(COUNTER_SOURCES.values()))),
    BASELINE_CONTRACT: ("linux", "sbi", "pfcp"),
}


def parse_time(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed


def _number(value: Any) -> bool:
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class CollectorHealth:
    heartbeat_at: datetime
    collector_healthy: bool
    telemetry_source_synced: bool
    observed_through: datetime

    def __post_init__(self) -> None:
        parse_time(self.heartbeat_at)
        parse_time(self.observed_through)
        if type(self.collector_healthy) is not bool or type(self.telemetry_source_synced) is not bool:
            raise ValueError("collector readiness flags must be booleans")


class TelemetryWindow:
    """Bounded tumbling window over cumulative counters and sampled Linux metrics."""

    def __init__(
        self, start: str | datetime, *, duration_sec: float = 10.0,
        heartbeat_timeout_sec: float = 2.0, minimum_linux_events: int = 2,
        max_samples: int = 10000,
        contract: str = FULL_CONTRACT,
    ):
        if contract not in CONTRACT_SOURCES:
            raise ValueError("unknown telemetry contract")
        if not _number(duration_sec) or duration_sec <= 0:
            raise ValueError("duration_sec must be finite and positive")
        if not _number(heartbeat_timeout_sec) or heartbeat_timeout_sec <= 0:
            raise ValueError("heartbeat_timeout_sec must be finite and positive")
        if type(minimum_linux_events) is not int or minimum_linux_events < 2:
            raise ValueError("minimum_linux_events must be at least two")
        if type(max_samples) is not int or max_samples < 2:
            raise ValueError("max_samples must be at least two")
        self.start = parse_time(start)
        self.end = self.start + timedelta(seconds=duration_sec)
        self.duration_sec = duration_sec
        self.heartbeat_timeout_sec = heartbeat_timeout_sec
        self.minimum_linux_events = minimum_linux_events
        self.max_samples = max_samples
        self.contract = contract
        self.primary_sources = CONTRACT_SOURCES[contract]
        self.counter_sources = {name: source for name, source in COUNTER_SOURCES.items() if source in self.primary_sources}
        self.availability_sources = {name: source for name, source in AVAILABILITY_SOURCES.items() if source in self.primary_sources}
        self.feature_names = ("duration_sec", *LINUX_FEATURES, *self.counter_sources, *self.availability_sources)
        self._samples: list[tuple[datetime, dict[str, float]]] = []
        self._health: dict[str, CollectorHealth] = {}
        self._collector_failures: set[str] = set()
        self._evidence_errors: set[str] = set()
        self._sealed = False
        self._lifecycle: list[dict[str, str]] = []

    def add_snapshot(
        self, observed_at: str | datetime, *, counters: dict[str, int],
        linux_sample: dict[str, float], collectors: dict[str, CollectorHealth],
    ) -> None:
        if self._sealed:
            raise ValueError("sealed windows cannot accept snapshots")
        timestamp = parse_time(observed_at)
        if not self.start <= timestamp <= self.end:
            raise ValueError("snapshot outside the window boundaries")
        if self._samples and timestamp <= self._samples[-1][0]:
            raise ValueError("snapshot timestamps must increase strictly")
        if len(self._samples) >= self.max_samples:
            raise ValueError("window sample limit reached")
        previous_time = self._samples[-1][0] if self._samples else self.start
        if (timestamp - previous_time).total_seconds() > self.heartbeat_timeout_sec:
            self._collector_failures.add("heartbeat coverage gap")
        if not self._samples and timestamp != self.start:
            self._evidence_errors.add("missing start-boundary counter baseline")
        for source in self.primary_sources:
            health = collectors.get(source)
            if health is None:
                self._collector_failures.add(f"missing handshake: {source}")
                continue
            age = (timestamp - health.heartbeat_at).total_seconds()
            previous_health = self._health.get(source)
            if (
                not health.collector_healthy or not health.telemetry_source_synced
                or not 0 <= age <= self.heartbeat_timeout_sec
                or health.observed_through != timestamp
                or (previous_health is not None and (
                    health.heartbeat_at < previous_health.heartbeat_at
                    or health.observed_through < previous_health.observed_through
                ))
            ):
                self._collector_failures.add(f"degraded, stale or unsynced collector: {source}")
            self._health[source] = health
        values: dict[str, float] = {}
        previous = self._samples[-1][1] if self._samples else {}
        for name in self.counter_sources:
            value = counters.get(name)
            if type(value) is not int or value < 0:
                self._evidence_errors.add(f"missing or invalid counter: {name}")
                continue
            values[name] = value
            if name in previous and value < previous[name]:
                self._evidence_errors.add(f"counter regression/reset: {name}")
        for name in ("load_1m", "memory_total", "memory_available"):
            value = linux_sample.get(name)
            if not _number(value) or value < 0:
                self._evidence_errors.add(f"missing or invalid Linux measurement: {name}")
            else:
                values[name] = value
        if "memory_total" in values and "memory_available" in values:
            if values["memory_total"] <= 0 or values["memory_available"] > values["memory_total"]:
                self._evidence_errors.add("invalid Linux memory bounds")
        self._samples.append((timestamp, values))

    def seal(self, observed_at: str | datetime) -> None:
        timestamp = parse_time(observed_at)
        if timestamp != self.end:
            raise ValueError("seal marker must match the configured end boundary")
        self._sealed = True

    def is_sealed(self, expected_duration_sec: float | None = None) -> bool:
        return self._sealed and (expected_duration_sec is None or expected_duration_sec == self.duration_sec)

    def inspect(self, now: str | datetime) -> dict[str, Any]:
        timestamp = parse_time(now)
        if timestamp < self.start or (self._samples and timestamp < self._samples[-1][0]):
            raise ValueError("readiness time precedes observed evidence")
        unavailable = set(self._collector_failures)
        for source in self.primary_sources:
            health = self._health.get(source)
            reference_time = self.end if self._sealed else timestamp
            if health is None or (reference_time - health.heartbeat_at).total_seconds() > self.heartbeat_timeout_sec:
                unavailable.add(f"missing or stale heartbeat: {source}")
        features: dict[str, float] = {}
        errors = set(self._evidence_errors)
        if unavailable:
            status = TelemetryStatus.COLLECTOR_UNAVAILABLE
        elif not self._sealed or timestamp < self.end:
            status = TelemetryStatus.ACCUMULATING
        elif not self._samples or self._samples[-1][0] != self.end:
            status = TelemetryStatus.INSUFFICIENT_EVIDENCE
            errors.add("missing end-boundary snapshot/watermarks")
        elif errors:
            status = TelemetryStatus.INSUFFICIENT_EVIDENCE
        else:
            first = self._samples[0][1]
            last = self._samples[-1][1]
            features = {name: last[name] - first[name] for name in self.counter_sources}
            if features["linux_event_count"] < self.minimum_linux_events:
                errors.add("minimum Linux event volume not reached")
            if features["linux_event_count"] != len(self._samples) - 1:
                errors.add("Linux counter does not match buffered samples")
            if features["sbi_error_event_count"] > features["sbi_event_count"]:
                errors.add("SBI error count exceeds total")
            if features["pfcp_request_count"] + features["pfcp_response_count"] > features["pfcp_event_count"]:
                errors.add("PFCP direction counts exceed total")
            if errors:
                features = {}
                status = TelemetryStatus.INSUFFICIENT_EVIDENCE
            else:
                samples = [values for _, values in self._samples[1:]]
                loads = [values["load_1m"] for values in samples]
                mean_load = sum(loads) / len(loads)
                features.update({
                    "duration_sec": self.duration_sec,
                    "linux_load_1m_mean": mean_load,
                    "linux_load_1m_std": math.sqrt(sum((value - mean_load) ** 2 for value in loads) / len(loads)),
                    "linux_load_1m_min": min(loads), "linux_load_1m_max": max(loads),
                    "linux_memory_total_mean": sum(values["memory_total"] for values in samples) / len(samples),
                    "linux_memory_available_mean": sum(values["memory_available"] for values in samples) / len(samples),
                    "memory_available_ratio_mean": sum(values["memory_available"] / values["memory_total"] for values in samples) / len(samples),
                    **{name: 1.0 for name in self.availability_sources},
                })
                status = TelemetryStatus.READY
        if not self._lifecycle or self._lifecycle[-1]["status"] != status.value:
            self._lifecycle.append({"observed_at": timestamp.isoformat(), "status": status.value})
        return {
            "contract": self.contract,
            "status": status.value, "window_start": self.start.isoformat(),
            "window_end": self.end.isoformat(), "sealed": self._sealed,
            "sample_count": len(self._samples), "features": features,
            "missing_features": sorted(set(self.feature_names) - set(features)),
            "collector_errors": sorted(unavailable), "evidence_errors": sorted(errors),
            "lifecycle": [dict(entry) for entry in self._lifecycle],
            "actionable": False,
        }