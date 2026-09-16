import unittest
from pathlib import Path

from nwdaf_research.pipeline import NWDAFPipeline


class NWDAFPipelineTests(unittest.TestCase):
    def setUp(self):
        self.raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
        self.pipeline = NWDAFPipeline(self.raw_root)

    def test_run_returns_scored_summary(self):
        summary = self.pipeline.run()
        self.assertIn("run_count", summary)
        self.assertIn("scores", summary)
        self.assertEqual(summary["run_count"], len(summary["scores"]))
        self.assertGreater(summary["run_count"], 0)

    def test_run_exports_json(self):
        export_path = Path(__file__).resolve().parents[1] / "evaluation" / "pipeline_scores.json"
        summary = self.pipeline.run(output_path=export_path)
        self.assertTrue(export_path.exists())
        self.assertEqual(summary["run_count"], len(summary["scores"]))


if __name__ == "__main__":
    unittest.main()
