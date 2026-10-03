from __future__ import annotations

import math
from typing import Any

from nwdaf_research.live.telemetry_window import CONTRACT_SOURCES, FULL_CONTRACT


class HeartbeatReadinessGate:
    """Validate one host/boot monotonic clock domain before window admission."""

    def __init__(
        self, clock_domain: str, *, heartbeat_interval_sec: float = 1.0,
        timeout_sec: float = 2.0, warmup_sec: float = 30.0,
        contract: str = FULL_CONTRACT,
    ):
        if contract not in CONTRACT_SOURCES:
            raise ValueError("unknown telemetry contract")
        if not isinstance(clock_domain, str) or not clock_domain.strip():
            raise ValueError("clock_domain must identify host/boot/CLOCK_MONOTONIC")
        for value in (heartbeat_interval_sec, timeout_sec, warmup_sec):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("heartbeat timing must be finite and positive")
        if timeout_sec > 2 * heartbeat_interval_sec:
            raise ValueError("timeout must not exceed twice the heartbeat interval")
        self.clock_domain = clock_domain
        self.timeout_ns = int(timeout_sec * 1_000_000_000)
        self.warmup_ns = int(warmup_sec * 1_000_000_000)
        self.contract = contract
        self.sources = CONTRACT_SOURCES[contract]
        self._latest: dict[str, dict[str, Any]] = {}
        self._first: dict[str, int] = {}
        self._faults: set[str] = set()

    def observe(self, source: str, heartbeat: dict[str, Any], *, received_at_ns: int) -> None:
        if source not in self.sources:
            raise ValueError("unknown primary source")
        if type(received_at_ns) is not int or received_at_ns < 0:
            raise ValueError("received_at_ns must be a monotonic nonnegative integer")
        try:
            if heartbeat["clock_domain"] != self.clock_domain or heartbeat["clock"] != "CLOCK_MONOTONIC":
                raise ValueError("clock domain mismatch")
            identity = heartbeat["source_id"]
            instance = heartbeat["collector_instance_id"]
            if not isinstance(identity, str) or not identity.strip() or not isinstance(instance, str) or not instance.strip():
                raise ValueError("missing source or collector instance identity")
            timestamp = heartbeat["timestamp_ns"]
            watermark = heartbeat["window_watermark_ns"]
            sequence = heartbeat["sequence_no"]
            events = heartbeat["metrics_summary"]["events_observed"]
            drops = heartbeat["metrics_summary"]["drops"]
            if any(type(value) is not int or value < 0 for value in (timestamp, watermark, sequence, events, drops)):
                raise ValueError("timestamps, sequence and counters must be nonnegative integers")
            if heartbeat["status"] != "HEALTHY" or drops != 0:
                raise ValueError("unhealthy or lossy collector")
            if not 0 <= received_at_ns - timestamp <= self.timeout_ns:
                raise ValueError("stale or future heartbeat")
            if not 0 <= timestamp - watermark <= self.timeout_ns:
                raise ValueError("future or lagging watermark")
            previous = self._latest.get(source)
            if previous is not None:
                if identity != previous["source_id"] or instance != previous["collector_instance_id"]:
                    raise ValueError("collector restart/identity change")
                if sequence <= previous["sequence_no"] or timestamp <= previous["timestamp_ns"]:
                    raise ValueError("out-of-order or duplicate heartbeat")
                if received_at_ns < previous["received_at_ns"] or received_at_ns - previous["received_at_ns"] > self.timeout_ns:
                    raise ValueError("heartbeat arrival coverage gap")
                if watermark < previous["window_watermark_ns"] or events < previous["events_observed"]:
                    raise ValueError("watermark or counter regression")
            self._first.setdefault(source, timestamp)
            self._latest[source] = {
                "source_id": identity, "collector_instance_id": instance,
                "timestamp_ns": timestamp, "window_watermark_ns": watermark,
                "sequence_no": sequence, "events_observed": events,
                "received_at_ns": received_at_ns,
            }
        except (KeyError, TypeError, ValueError) as error:
            self._faults.add(f"{source}: {error}")

    def inspect(self, now_ns: int) -> dict[str, Any]:
        if type(now_ns) is not int or now_ns < 0:
            raise ValueError("now_ns must be a monotonic nonnegative integer")
        if any(now_ns < row["received_at_ns"] for row in self._latest.values()):
            raise ValueError("readiness time precedes receipt")
        errors = set(self._faults)
        missing = sorted(set(self.sources) - set(self._latest))
        errors.update(f"missing source: {source}" for source in missing)
        for source, row in self._latest.items():
            if now_ns - row["timestamp_ns"] > self.timeout_ns or now_ns - row["window_watermark_ns"] > self.timeout_ns:
                errors.add(f"stale heartbeat/watermark: {source}")
                self._faults.add(f"stale heartbeat/watermark: {source}")
        shared_duration = 0
        if not missing:
            shared_duration = max(0, min(row["window_watermark_ns"] for row in self._latest.values()) - max(self._first.values()))
        return {
            "contract": self.contract,
            "status": "COLLECTOR_UNAVAILABLE" if errors else (
                "READY" if shared_duration >= self.warmup_ns else "WARMING_UP"
            ),
            "clock_domain": self.clock_domain, "clock": "CLOCK_MONOTONIC",
            "healthy_coverage_sec": shared_duration / 1_000_000_000,
            "required_coverage_sec": self.warmup_ns / 1_000_000_000,
            "errors": sorted(errors), "actionable": False,
        }