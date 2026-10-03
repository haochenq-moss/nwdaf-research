import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from nwdaf_research.input_testing.anomaly_dataset import load_anomaly_dataset


class SimulatedAnomalyDemoTests(unittest.TestCase):
    def test_demo_runs_and_cannot_silently_enter_real_pipeline(self):
        path = Path(__file__).resolve().parents[1] / "scripts/run_simulated_anomaly_demo.py"
        spec = importlib.util.spec_from_file_location("simulation_demo", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "demo"
            summary = module.run_demo(root)
            self.assertTrue(summary["simulation_only"])
            self.assertFalse(summary["research_result"])
            self.assertEqual(summary["train_runs"], 36)
            self.assertEqual(summary["held_out_runs"], 18)
            self.assertEqual(summary["feature_count"], 16)
            with self.assertRaisesRegex(ValueError, "explicit allow_simulation"):
                load_anomaly_dataset(root / "dataset.json", root / "plan.json")
            result = json.loads((root / "results.json").read_text())
            self.assertTrue(result["simulation_only"])
            self.assertFalse(result["research_result"])
            with self.assertRaises(FileExistsError):
                module.run_demo(root)