import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class TrialSummaryTests(unittest.TestCase):
    def test_summarizer_reports_unavailable_for_missing_series(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            result = subprocess.run(
                ["python", str(root / "scripts/summarize_live_trials.py"), "--output", str(output)],
                capture_output=True,
                text=True,
                check=True,
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["B0"]["rtt_mean_ms"]["status"], "unavailable")
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()