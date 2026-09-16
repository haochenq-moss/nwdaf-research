import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class SupplementalValidationTests(unittest.TestCase):
    def test_validator_help_is_available(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["python", str(root / "scripts/validate_supplemental.py"), "--help"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("--root", result.stdout)


if __name__ == "__main__":
    unittest.main()