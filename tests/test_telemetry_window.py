import unittest
from datetime import datetime, timedelta, timezone

from nwdaf_research.live.telemetry_window import (
    COUNTER_SOURCES, WINDOW_FEATURES, CollectorHealth, TelemetryWindow,
)


class TelemetryWindowTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 3, tzinfo=timezone.utc)
        self.window = TelemetryWindow(self.start, duration_sec=2, heartbeat_timeout_sec=1)

    def add(self, second, *, linux_count=None, changes=None, degraded=None, missing=None, frozen=None):
        timestamp = self.start + timedelta(seconds=second)
        counters = {name: 100 for name in COUNTER_SOURCES}
        counters["linux_event_count"] += second if linux_count is None else linux_count
        counters.update(changes or {})
        health = {source: CollectorHealth(timestamp, source != degraded, True, timestamp)
                  for source in self.window.primary_sources if source != missing}
        if frozen is not None:
            health[frozen] = CollectorHealth(self.start, True, True, timestamp)
        self.window.add_snapshot(timestamp, counters=counters,
                                 linux_sample={"load_1m": second, "memory_total": 100, "memory_available": 40},
                                 collectors=health)

    def complete(self):
        for second in range(3):
            self.add(second)
        self.window.seal(self.window.end)

    def test_complete_window_has_full_contract_and_valid_network_zeroes(self):
        self.complete()
        result = self.window.inspect(self.window.end)
        self.assertEqual(result["status"], "READY")
        self.assertEqual(set(result["features"]), set(WINDOW_FEATURES))
        self.assertEqual(result["features"]["sbi_event_count"], 0)
        self.assertEqual(result["features"]["sbi_telemetry_available"], 1)
        self.assertEqual(result["features"]["linux_load_1m_mean"], 1.5)
        self.assertEqual(result["features"]["linux_load_1m_std"], 0.5)
        self.assertEqual(result["missing_features"], [])

    def test_healthy_unsealed_window_accumulates(self):
        self.add(0)
        self.assertEqual(self.window.inspect(self.start)["status"], "ACCUMULATING")

    def test_missing_or_degraded_collector_immediately_abstains(self):
        for kwargs in ({"missing": "sbi"}, {"degraded": "pfcp"}):
            with self.subTest(kwargs=kwargs):
                self.setUp()
                self.add(0, **kwargs)
                result = self.window.inspect(self.start)
                self.assertEqual(result["status"], "COLLECTOR_UNAVAILABLE")
                self.assertEqual(result["features"], {})

    def test_regression_invalidates_whole_window(self):
        self.add(0)
        self.add(1, changes={"sbi_event_count": 99})
        self.add(2)
        self.window.seal(self.window.end)
        result = self.window.inspect(self.window.end)
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertTrue(any("regression" in value for value in result["evidence_errors"]))

    def test_recovered_collector_cannot_hide_earlier_failure(self):
        self.add(0, degraded="sbi")
        self.add(1)
        self.add(2)
        self.window.seal(self.window.end)
        self.assertEqual(self.window.inspect(self.window.end)["status"], "COLLECTOR_UNAVAILABLE")

    def test_stale_heartbeat_and_cadence_gap_block(self):
        self.add(0)
        self.assertEqual(self.window.inspect(self.window.end)["status"], "COLLECTOR_UNAVAILABLE")
        self.add(2)
        self.window.seal(self.window.end)
        self.assertEqual(self.window.inspect(self.window.end)["status"], "COLLECTOR_UNAVAILABLE")

    def test_low_volume_blocks_even_when_sealed(self):
        self.add(0)
        self.add(1, linux_count=0)
        self.add(2, linux_count=1)
        self.window.seal(self.window.end)
        self.assertEqual(self.window.inspect(self.window.end)["status"], "INSUFFICIENT_EVIDENCE")

    def test_invalid_measurement_blocks(self):
        timestamp = self.start
        health = {source: CollectorHealth(timestamp, True, True, timestamp) for source in self.window.primary_sources}
        self.window.add_snapshot(timestamp, counters={name: 0 for name in COUNTER_SOURCES},
                                 linux_sample={"load_1m": float("nan"), "memory_total": 100, "memory_available": 40},
                                 collectors=health)
        self.add(1)
        self.add(2)
        self.window.seal(self.window.end)
        self.assertEqual(self.window.inspect(self.window.end)["status"], "INSUFFICIENT_EVIDENCE")

    def test_seal_and_order_boundaries(self):
        self.add(0)
        with self.assertRaises(ValueError):
            self.add(0)
        with self.assertRaises(ValueError):
            self.window.seal(self.start)
        self.add(1)
        self.add(2)
        self.window.seal(self.window.end)
        self.assertTrue(self.window.is_sealed(2))
        self.assertFalse(self.window.is_sealed(3))
        with self.assertRaises(ValueError):
            self.add(2)

    def test_configuration_rejects_nonfinite_and_boolean_values(self):
        for duration in (True, 0, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                TelemetryWindow(self.start, duration_sec=duration)

    def test_missing_counter_is_not_filled_with_zero(self):
        timestamp = self.start
        counters = {name: 0 for name in COUNTER_SOURCES if name != "sbi_event_count"}
        health = {source: CollectorHealth(timestamp, True, True, timestamp) for source in self.window.primary_sources}
        self.window.add_snapshot(timestamp, counters=counters,
                                 linux_sample={"load_1m": 0, "memory_total": 100, "memory_available": 40},
                                 collectors=health)
        self.add(1)
        self.add(2)
        self.window.seal(self.window.end)
        result = self.window.inspect(self.window.end)
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result["features"], {})

    def test_boolean_handshake_is_strict(self):
        with self.assertRaises(ValueError):
            CollectorHealth(self.start, 1, True, self.start)

    def test_unsynced_or_future_watermark_blocks(self):
        for watermark in (self.start - timedelta(seconds=1), self.start + timedelta(seconds=1)):
            with self.subTest(watermark=watermark):
                self.setUp()
                health = {source: CollectorHealth(self.start, True, True, watermark)
                          for source in self.window.primary_sources}
                self.window.add_snapshot(self.start, counters={name: 0 for name in COUNTER_SOURCES},
                                         linux_sample={"load_1m": 0, "memory_total": 100, "memory_available": 40},
                                         collectors=health)
                self.assertEqual(self.window.inspect(self.start)["status"], "COLLECTOR_UNAVAILABLE")

    def test_late_or_missing_start_boundary_blocks(self):
        self.add(1)
        self.add(2)
        self.window.seal(self.window.end)
        self.assertEqual(self.window.inspect(self.window.end)["status"], "INSUFFICIENT_EVIDENCE")

    def test_missing_end_boundary_blocks(self):
        self.add(0)
        self.add(1)
        self.window.seal(self.window.end)
        self.assertEqual(self.window.inspect(self.window.end)["status"], "INSUFFICIENT_EVIDENCE")

    def test_sample_limit_is_enforced(self):
        self.window.max_samples = 2
        self.add(0)
        self.add(1)
        with self.assertRaisesRegex(ValueError, "sample limit"):
            self.add(2)

    def test_one_frozen_secondary_heartbeat_becomes_unavailable(self):
        self.add(0)
        self.add(1, frozen="ebpf")
        self.assertEqual(self.window.inspect(self.start + timedelta(seconds=1))["status"], "ACCUMULATING")
        self.add(2, frozen="ebpf")
        report = self.window.inspect(self.window.end)
        self.assertEqual(report["status"], "COLLECTOR_UNAVAILABLE")
        self.assertTrue(any("ebpf" in error for error in report["collector_errors"]))
        self.assertEqual(report["features"], {})

    def test_process_restart_decreasing_counter_rejects_sealed_window(self):
        self.add(0)
        self.add(1, changes={"process_event_count": 0})
        self.add(2, changes={"process_event_count": 1})
        self.window.seal(self.window.end)
        report = self.window.inspect(self.window.end)
        self.assertEqual(report["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("counter regression/reset: process_event_count", report["evidence_errors"])
        self.assertEqual(report["features"], {})