import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class ConfigurationSummaryTests(unittest.TestCase):
    def test_summary_accepts_configuration_report(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "trial.json"
            output = Path(directory) / "summary.json"
            source.write_text(json.dumps({
                "B0": {"network_measurement": {"rtt_mean_ms": 1.0, "packet_loss_percent": 0.0, "throughput": {"sent_bps": 10.0, "received_bps": 9.0}}},
                "B1": {"detection_latency_ms": 2.0, "network_measurement": {"rtt_mean_ms": 1.1, "packet_loss_percent": 0.0, "throughput": {"sent_bps": 8.0, "received_bps": 7.0}}},
            }), encoding="utf-8")
            result = subprocess.run(
                ["python", str(root / "scripts/summarize_configuration_trials.py"), str(source), "--output", str(output)],
                capture_output=True, text=True, check=True,
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["trial_count"], 1)
            self.assertEqual(report["B1"]["detection_latency_ms"]["mean"], 2.0)


if __name__ == "__main__":
    unittest.main()