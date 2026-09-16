import unittest
from pathlib import Path

from nwdaf_research.preprocessing.features import RunFeatureBuilder


class RunFeatureBuilderTests(unittest.TestCase):
    def setUp(self):
        self.raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
        self.builder = RunFeatureBuilder(self.raw_root)

    def test_build_features_for_run(self):
        features = self.builder.build_features_for_run("R00001")
        self.assertEqual(features["run_id"], "R00001")
        self.assertIn("linux_event_count", features)
        self.assertIn("ground_truth_class", features)
        self.assertEqual(features["ground_truth_class"], "normal")
        self.assertGreater(features["linux_event_count"], 0)

    def test_build_features_includes_derived_linux_signals(self):
        features = self.builder.build_features_for_run("R00001")
        self.assertIn("linux_load_1m_std", features)
        self.assertIn("memory_available_ratio_mean", features)
        self.assertIn("process_event_by_type", features)
        self.assertIn("host_event_type_counts", features)

    def test_build_features_tracks_network_telemetry_availability(self):
        features = self.builder.build_features_for_run("R00001")
        self.assertIn("sbi_event_count", features)
        self.assertIn("pfcp_event_count", features)
        self.assertEqual(features["sbi_telemetry_available"], 0.0)
        self.assertEqual(features["pfcp_telemetry_available"], 0.0)


if __name__ == "__main__":
    unittest.main()
