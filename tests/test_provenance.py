import json
import tempfile
import unittest
from pathlib import Path

from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer


class ProvenanceTests(unittest.TestCase):
    def test_model_artifact_contains_dataset_and_feature_provenance(self):
        raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
        with tempfile.TemporaryDirectory() as directory:
            manifest = NWDAFResearchAnalyzer(raw_root).save_model_artifact(directory)
            manifest_path = Path(directory) / "manifest.json"
            model_path = Path(directory) / "model.pkl"
            self.assertTrue(manifest_path.exists())
            self.assertTrue(model_path.exists())
            persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["model"]["version"], "rf-v1")
            self.assertEqual(persisted["training"]["split_policy"], "whole-run")
            self.assertTrue(persisted["dataset"]["archive_sha256"])
            self.assertEqual(manifest["feature_schema"]["name"], "run-linux-v1")
            self.assertIn("linux_event_count", manifest["feature_schema"]["features"])


if __name__ == "__main__":
    unittest.main()