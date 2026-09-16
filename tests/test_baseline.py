import unittest
from pathlib import Path

from nwdaf_research.analytics.baseline import BaselineAnomalyModel


class BaselineAnomalyModelTests(unittest.TestCase):
    def setUp(self):
        self.raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
        self.model = BaselineAnomalyModel(self.raw_root)

    def test_prepare_dataset_returns_expected_split_counts(self):
        dataset = self.model.prepare_dataset()
        self.assertIn("train", dataset)
        self.assertIn("val", dataset)
        self.assertIn("test", dataset)
        self.assertEqual(len(dataset["train"]["y"]), 60)
        self.assertEqual(len(dataset["val"]["y"]), 20)
        self.assertEqual(len(dataset["test"]["y"]), 10)

    def test_train_and_evaluate_returns_metrics(self):
        metrics = self.model.train_and_evaluate()
        self.assertIn("accuracy", metrics)
        self.assertIn("f1", metrics)
        self.assertIn("test_count", metrics)
        self.assertGreaterEqual(metrics["accuracy"], 0.0)
        self.assertLessEqual(metrics["accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
