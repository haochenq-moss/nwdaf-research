import subprocess
import unittest
from pathlib import Path


class PaperResultsTests(unittest.TestCase):
    def test_generator_help_is_available(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["python", str(root / "scripts/generate_paper_results.py"), "--help"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("--summary", result.stdout)


if __name__ == "__main__":
    unittest.main()