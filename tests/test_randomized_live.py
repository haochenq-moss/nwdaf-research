import subprocess
import unittest
from pathlib import Path


class RandomizedLiveTests(unittest.TestCase):
    def test_randomized_script_help(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(["python", str(root / "scripts/measure_randomized_live.py"), "--help"], capture_output=True, text=True, check=True)
        self.assertIn("--seed", result.stdout)


if __name__ == "__main__":
    unittest.main()