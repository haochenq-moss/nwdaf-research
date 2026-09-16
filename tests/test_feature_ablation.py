import unittest
from pathlib import Path

from nwdaf_research.analytics.baseline import BaselineAnomalyModel


class BaselineFeatureAblationTests(unittest.TestCase):
    def setUp(self):
        self.raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
        self.model = BaselineAnomalyModel(self.raw_root)

    def test_feature_ablation_returns_summary_for_key_groups(self):
        summaries = self.model.evaluate_feature_ablation()
        self.assertIn("full", summaries)
        self.assertIn("linux_load", summaries)
        self.assertIn("memory", summaries)
        self.assertIn("runtime", summaries)
        self.assertIn("accuracy", summaries["full"])
        self.assertGreaterEqual(summaries["full"]["accuracy"], 0.0)
        self.assertLessEqual(summaries["full"]["accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
