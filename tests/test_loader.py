import unittest
from pathlib import Path

from nwdaf_research.ingestion.loader import DatasetLoader


class DatasetLoaderTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / "data" / "raw"
        self.loader = DatasetLoader(self.root)

    def test_discovers_all_runs(self):
        runs = self.loader.discover_runs()
        self.assertEqual(len(runs), 90)
        self.assertIn("R00001", runs)
        self.assertIn("R00090", runs)

    def test_load_run_includes_metadata_ground_truth_and_linux_events(self):
        run = self.loader.load_run("R00001")
        self.assertEqual(run["run_id"], "R00001")
        self.assertEqual(run["ground_truth"]["scenario_id"], "NORMAL")
        self.assertIn("linux", run["telemetry"])
        self.assertGreater(len(run["telemetry"]["linux"]), 0)
        self.assertIn("split", run)

    def test_split_manifest_is_loaded(self):
        manifest = self.loader.load_split_manifest()
        self.assertEqual(manifest["counts"]["train"], 60)
        self.assertEqual(manifest["counts"]["val"], 20)
        self.assertEqual(manifest["counts"]["test"], 10)

    def test_alternate_split_manifest_name_is_supported(self):
        alternate_root = self.root.parent / "supplemental_large_raw"
        if alternate_root.exists():
            loader = DatasetLoader(alternate_root)
            manifest = loader.load_split_manifest()
            self.assertEqual(manifest["counts"]["test"], 20)


if __name__ == "__main__":
    unittest.main()
