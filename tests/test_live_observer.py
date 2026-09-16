import json
import unittest
from unittest.mock import patch

from nwdaf_research.live.ssh_observer import SSHLiveObserver


class LiveObserverTests(unittest.TestCase):
    @patch("nwdaf_research.live.ssh_observer.subprocess.run")
    def test_maps_only_real_snapshot_values(self, run):
        run.return_value.stdout = json.dumps(
            {
                "load_1m": 1.5,
                "memory_total": 1000,
                "memory_available": 250,
                "process_count": 42,
                "ue_tunnel_count": 1,
                "listening_socket_count": 12,
                "pfcp_recent_log_events": 4,
                "sbi_recent_log_events": 6,
            }
        )
        observation = SSHLiveObserver().observe()
        self.assertEqual(observation.features["linux_load_1m_mean"], 1.5)
        self.assertEqual(observation.features["memory_available_ratio_mean"], 0.25)
        self.assertEqual(observation.evidence["ue_tunnel_count"], 1)
        self.assertEqual(observation.evidence["pfcp_recent_log_events"], 4)
        self.assertEqual(observation.evidence["event_count_window"], "tail-2000-log-lines")
        self.assertIn("sbi_event_rate", observation.unavailable_features)
        self.assertFalse(observation.complete_for_autonomous_response)
        command = run.call_args.args[0]
        self.assertIn("BatchMode=yes", command)


if __name__ == "__main__":
    unittest.main()