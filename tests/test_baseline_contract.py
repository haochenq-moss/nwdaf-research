import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer
from nwdaf_research.live.heartbeat import HeartbeatReadinessGate
from nwdaf_research.live.telemetry_window import BASELINE_CONTRACT, CollectorHealth, TelemetryWindow


class BaselineContractTests(unittest.TestCase):
    def complete_window(self, missing=None):
        start = datetime(2026, 10, 3, tzinfo=timezone.utc)
        window = TelemetryWindow(start, duration_sec=2, contract=BASELINE_CONTRACT)
        for offset in range(3):
            timestamp = start + timedelta(seconds=offset)
            counters = {name: 0 for name in window.counter_sources}
            counters["linux_event_count"] = offset
            health = {source: CollectorHealth(timestamp, True, True, timestamp)
                      for source in window.primary_sources if source != missing}
            window.add_snapshot(timestamp, counters=counters,
                                linux_sample={"load_1m": 0.1, "memory_total": 100, "memory_available": 40},
                                collectors=health)
            window.inspect(timestamp)
        window.seal(window.end)
        return window

    def test_explicit_baseline_has_sixteen_features_without_fabricated_sources(self):
        window = self.complete_window()
        report = window.inspect(window.end)
        self.assertEqual(report["contract"], BASELINE_CONTRACT)
        self.assertEqual(report["status"], "READY")
        self.assertEqual(len(report["features"]), 16)
        self.assertNotIn("ebpf_event_count", report["features"])
        self.assertNotIn("process_event_count", report["features"])
        self.assertNotIn("free5gc_event_count", report["features"])

    def test_baseline_still_requires_its_network_sources(self):
        window = self.complete_window(missing="pfcp")
        self.assertEqual(window.inspect(window.end)["status"], "COLLECTOR_UNAVAILABLE")

    def test_historical_model_cannot_score_reduced_contract(self):
        window = self.complete_window()
        analyzer = NWDAFResearchAnalyzer.__new__(NWDAFResearchAnalyzer)
        analyzer._train_model = Mock()
        result = analyzer.score_live_window(window, now=window.end.isoformat())
        self.assertEqual(result["status"], "MODEL_NOT_APPROVED")
        self.assertFalse(result["inference_performed"])
        analyzer._train_model.assert_not_called()

    def test_heartbeat_profile_is_explicit_and_default_is_unchanged(self):
        baseline = HeartbeatReadinessGate("host/boot/CLOCK_MONOTONIC", contract=BASELINE_CONTRACT)
        self.assertEqual(set(baseline.sources), {"linux", "sbi", "pfcp"})
        self.assertEqual(len(HeartbeatReadinessGate("host/boot/CLOCK_MONOTONIC").sources), 6)
        self.assertEqual(len(TelemetryWindow("2026-10-03T00:00:00Z").primary_sources), 6)

    def test_unknown_contract_is_rejected(self):
        with self.assertRaises(ValueError):
            TelemetryWindow("2026-10-03T00:00:00Z", contract="silently-disabled-ebpf")