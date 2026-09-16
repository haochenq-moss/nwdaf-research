import unittest
from pathlib import Path

from nwdaf_research.analytics.scenario_baseline import ScenarioBaselineModel


class ScenarioBaselineModelTests(unittest.TestCase):
    def test_prepare_dataset_returns_expected_split_shapes(self):
        model = ScenarioBaselineModel(Path(__file__).resolve().parents[1] / "data" / "raw")
        dataset = model.prepare_dataset()
        self.assertIn("train", dataset)
        self.assertIn("val", dataset)
        self.assertIn("test", dataset)
        self.assertEqual(len(dataset["train"]["y"]), 60)
        self.assertEqual(len(dataset["val"]["y"]), 20)
        self.assertEqual(len(dataset["test"]["y"]), 10)

    def test_train_and_evaluate_returns_metrics(self):
        model = ScenarioBaselineModel(Path(__file__).resolve().parents[1] / "data" / "raw")
        metrics = model.train_and_evaluate()
        self.assertIn("macro_f1", metrics)
        self.assertIn("accuracy", metrics)
        self.assertIn("test_count", metrics)


if __name__ == "__main__":
    unittest.main()
