import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import numpy as np

from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer
from nwdaf_research.live.telemetry_window import COUNTER_SOURCES, WINDOW_FEATURES, CollectorHealth, TelemetryWindow


class LiveFeatureCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = NWDAFResearchAnalyzer.__new__(NWDAFResearchAnalyzer)
        self.analyzer._train_model = Mock()
        self.analyzer._feature_names = ["linux_load_1m_mean", "linux_event_count"]
        self.analyzer._trained_model = Mock()
        self.analyzer._trained_model.predict_proba.return_value = np.array([[0.8, 0.2]])

    def test_missing_feature_abstains_before_prediction(self):
        result = self.analyzer.score_live_features(
            {"linux_load_1m_mean": 1.0}, unavailable_features=[],
        )
        self.assertEqual(result["predicted_label"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(result["anomaly_probability"])
        self.assertEqual(result["feature_compatibility"]["missing_features"], ["linux_event_count"])
        self.analyzer._trained_model.predict_proba.assert_not_called()

    def test_explicitly_unavailable_measurement_abstains(self):
        result = self.analyzer.score_live_features(
            {"linux_load_1m_mean": 1.0, "linux_event_count": 3.0},
            unavailable_features=["linux_load_1m_std_over_window"],
        )
        self.assertFalse(result["inference_performed"])
        self.analyzer._trained_model.predict_proba.assert_not_called()

    def test_nonfinite_invalid_and_boolean_values_abstain(self):
        for value in (float("nan"), float("inf"), None, "invalid", True):
            with self.subTest(value=value):
                result = self.analyzer.score_live_features(
                    {"linux_load_1m_mean": value, "linux_event_count": 3.0},
                    unavailable_features=[],
                )
                self.assertEqual(result["feature_compatibility"]["invalid_features"], ["linux_load_1m_mean"])
        self.analyzer._trained_model.predict_proba.assert_not_called()

    def test_complete_vector_scores_but_never_authorizes_response(self):
        result = self.analyzer.score_live_features(
            {"linux_load_1m_mean": 1.0, "linux_event_count": 3.0},
            unavailable_features=[],
        )
        self.assertTrue(result["inference_performed"])
        self.assertEqual(result["predicted_label"], "NORMAL")
        self.assertFalse(result["actionable"])
        self.analyzer._trained_model.predict_proba.assert_called_once()

    def test_empty_feature_contract_abstains(self):
        self.analyzer._feature_names = []
        result = self.analyzer.score_live_features({}, unavailable_features=[])
        self.assertFalse(result["inference_performed"])
        self.analyzer._trained_model.predict_proba.assert_not_called()

    def test_window_health_gate_skips_training_and_inference(self):
        window = TelemetryWindow("2026-10-03T00:00:00Z")
        result = self.analyzer.score_live_window(window, now="2026-10-03T00:00:00Z")
        self.assertEqual(result["predicted_label"], "COLLECTOR_UNAVAILABLE")
        self.analyzer._train_model.assert_not_called()
        self.analyzer._trained_model.predict_proba.assert_not_called()

    def test_three_consecutive_healthy_zero_windows_complete_inference(self):
        self.analyzer._feature_names = list(WINDOW_FEATURES)
        first_start = datetime(2026, 10, 3, tzinfo=timezone.utc)
        for index in range(3):
            start = first_start + timedelta(seconds=2 * index)
            window = TelemetryWindow(start, duration_sec=2, heartbeat_timeout_sec=1)
            lifecycle = []
            for offset in range(3):
                timestamp = start + timedelta(seconds=offset)
                counters = {name: 0 for name in COUNTER_SOURCES}
                counters["linux_event_count"] = index * 2 + offset
                health = {source: CollectorHealth(timestamp, True, True, timestamp)
                          for source in window.primary_sources}
                window.add_snapshot(timestamp, counters=counters,
                                    linux_sample={"load_1m": 0.1, "memory_total": 100, "memory_available": 40},
                                    collectors=health)
                if offset == 0:
                    lifecycle.append(window.inspect(timestamp)["status"])
            window.seal(window.end)
            readiness = window.inspect(window.end)
            lifecycle.append(readiness["status"])
            self.assertEqual(len(readiness["features"]), 21)
            for name in COUNTER_SOURCES:
                if name != "linux_event_count":
                    self.assertEqual(readiness["features"][name], 0)
            result = self.analyzer.score_live_window(window, now=window.end.isoformat())
            lifecycle.append(result["status"])
            self.assertEqual(lifecycle, ["ACCUMULATING", "READY", "INFERENCE_COMPLETE"])
            self.assertEqual([entry["status"] for entry in result["lifecycle"]], lifecycle)
            self.assertTrue(result["inference_performed"])
            self.assertFalse(result["actionable"])
        self.assertEqual(self.analyzer._trained_model.predict_proba.call_count, 3)