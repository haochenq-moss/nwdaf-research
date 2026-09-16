import unittest
from pathlib import Path

from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer


class NWDAFResearchAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
        self.analyzer = NWDAFResearchAnalyzer(self.raw_root)

    def test_score_run_returns_prediction_and_probability(self):
        summary = self.analyzer.score_run("R00001")
        self.assertIn("run_id", summary)
        self.assertIn("predicted_label", summary)
        self.assertIn("anomaly_probability", summary)
        self.assertEqual(summary["run_id"], "R00001")
        self.assertIn(summary["predicted_label"], {"NORMAL", "ANOMALY"})
        self.assertGreaterEqual(summary["anomaly_probability"], 0.0)
        self.assertLessEqual(summary["anomaly_probability"], 1.0)

    def test_evaluate_returns_metrics(self):
        metrics = self.analyzer.evaluate()
        self.assertIn("accuracy", metrics)
        self.assertIn("f1", metrics)
        self.assertIn("test_count", metrics)


if __name__ == "__main__":
    unittest.main()
