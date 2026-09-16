import subprocess
import unittest
from pathlib import Path


class SupplementalNetworkTests(unittest.TestCase):
    def test_evaluator_help_is_available(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["python", str(root / "scripts/evaluate_supplemental_network.py"), "--help"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("--root", result.stdout)

    def test_split_help_is_available(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["python", str(root / "scripts/split_supplemental.py"), "--help"],
            capture_output=True, text=True, check=True
        )
        self.assertIn("--seed", result.stdout)


if __name__ == "__main__":
    unittest.main()