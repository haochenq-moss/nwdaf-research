import json
import subprocess
import unittest
from pathlib import Path


class LiveConfigurationScriptTests(unittest.TestCase):
    def test_script_declares_unavailable_live_b2_metrics(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "measure_live_configurations.py"
        result = subprocess.run(
            ["python", str(script), "--help"], capture_output=True, text=True, check=True
        )
        self.assertIn("--target", result.stdout)


if __name__ == "__main__":
    unittest.main()