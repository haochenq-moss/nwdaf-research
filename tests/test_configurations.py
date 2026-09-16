import unittest
from pathlib import Path

from nwdaf_research.experiments.configurations import evaluate_configurations


class ConfigurationEvaluationTests(unittest.TestCase):
    def test_reports_b0_b1_b2_and_unavailable_live_metrics(self):
        raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
        result = evaluate_configurations(str(raw_root))
        configurations = result["configurations"]
        self.assertEqual(set(configurations), {"B0", "B1", "B2"})
        self.assertEqual(configurations["B1"]["metrics"]["test_count"], 10)
        self.assertIn("per_scenario", configurations["B1"])
        self.assertEqual(
            configurations["B2"]["mitigation_metrics"]["recovery_time"],
            "unavailable",
        )


if __name__ == "__main__":
    unittest.main()