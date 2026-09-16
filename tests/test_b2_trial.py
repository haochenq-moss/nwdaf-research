import subprocess
import unittest
from pathlib import Path


class B2TrialTests(unittest.TestCase):
    def test_trial_requires_explicit_secret_environment(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "run_live_b2_alert.py"
        result = subprocess.run(
            ["python", str(script)], capture_output=True, text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RESPONSE_AGENT_API_KEY", result.stderr)


if __name__ == "__main__":
    unittest.main()