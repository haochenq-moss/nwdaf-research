import subprocess
import unittest
from pathlib import Path


class B2RateTrialTests(unittest.TestCase):
    def test_remote_runner_help_compiles(self):
        root = Path(__file__).resolve().parents[1]
        subprocess.run(["python", "-m", "py_compile", str(root / "scripts/run_b2_rate_trials_remote.py")], check=True)


if __name__ == "__main__":
    unittest.main()