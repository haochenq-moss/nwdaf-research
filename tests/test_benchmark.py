import json
import unittest
from unittest.mock import patch

from nwdaf_research.live.benchmark import SSHBaselineBenchmark


class BenchmarkTests(unittest.TestCase):
    @patch("nwdaf_research.live.benchmark.subprocess.run")
    def test_parses_measured_latency_and_loss(self, run):
        run.return_value.stdout = json.dumps({
            "status": "measured", "interface": "ueTun0", "target": "127.0.0.1",
            "ping_count": 3, "packet_loss_percent": "0", "rtt_mean_ms": "0.42",
            "throughput_status": "unavailable",
        })
        result = SSHBaselineBenchmark().measure(target="127.0.0.1", count=3)
        self.assertEqual(result.interface, "ueTun0")
        self.assertEqual(result.packet_loss_percent, 0.0)
        self.assertEqual(result.rtt_mean_ms, 0.42)
        self.assertEqual(result.throughput_status, "unavailable")
        self.assertIn("sh", run.call_args.args[0])

    def test_rejects_unbounded_probe_count(self):
        with self.assertRaises(ValueError):
            SSHBaselineBenchmark().measure(count=61)

    def test_packet_loss_remains_measured_when_all_packets_are_lost(self):
        self.assertEqual(
            SSHBaselineBenchmark()._parse_result(
                {
                    "status": "measured",
                    "interface": "ueTun0",
                    "packet_loss_percent": "100",
                    "rtt_mean_ms": "",
                    "throughput_status": "unavailable",
                },
                "8.8.8.8",
                3,
            ).packet_loss_percent,
            100.0,
        )


if __name__ == "__main__":
    unittest.main()