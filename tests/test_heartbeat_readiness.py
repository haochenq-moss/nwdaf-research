import unittest

from nwdaf_research.live.heartbeat import HeartbeatReadinessGate


class HeartbeatReadinessTests(unittest.TestCase):
    def setUp(self):
        self.gate = HeartbeatReadinessGate("lab-host/boot-id/CLOCK_MONOTONIC")

    def report(self, source, second):
        return {
            "source_id": source + "_01", "collector_instance_id": "instance-1",
            "clock_domain": self.gate.clock_domain, "clock": "CLOCK_MONOTONIC",
            "status": "HEALTHY", "timestamp_ns": second * 1_000_000_000,
            "sequence_no": second, "window_watermark_ns": second * 1_000_000_000,
            "metrics_summary": {"events_observed": second, "drops": 0},
        }

    def feed(self, second):
        for source in self.gate.sources:
            self.gate.observe(source, self.report(source, second), received_at_ns=second * 1_000_000_000)

    def test_all_six_sources_need_full_shared_thirty_seconds(self):
        for second in range(30):
            self.feed(second)
        self.assertEqual(self.gate.inspect(29_000_000_000)["status"], "WARMING_UP")
        self.feed(30)
        report = self.gate.inspect(30_000_000_000)
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["healthy_coverage_sec"], 30)

    def test_missing_source_immediately_unavailable(self):
        self.assertEqual(self.gate.inspect(0)["status"], "COLLECTOR_UNAVAILABLE")

    def test_stale_source_and_recovery_do_not_hide_gap(self):
        self.feed(0)
        self.assertEqual(self.gate.inspect(3_000_000_000)["status"], "COLLECTOR_UNAVAILABLE")
        self.feed(3)
        self.assertEqual(self.gate.inspect(3_000_000_000)["status"], "COLLECTOR_UNAVAILABLE")

    def test_sequence_counter_restart_clock_drop_and_watermark_fail_closed(self):
        mutations = (
            lambda row: row.update(sequence_no=0),
            lambda row: row.update(collector_instance_id="new-process"),
            lambda row: row.update(clock="CLOCK_REALTIME"),
            lambda row: row.update(clock_domain="another-host/boot/CLOCK_MONOTONIC"),
            lambda row: row.update(window_watermark_ns=3_000_000_000),
            lambda row: row["metrics_summary"].update(drops=1),
            lambda row: row["metrics_summary"].update(events_observed=0),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.setUp()
                self.feed(1)
                report = self.report("ebpf", 2)
                mutation(report)
                self.gate.observe("ebpf", report, received_at_ns=2_000_000_000)
                self.assertEqual(self.gate.inspect(2_000_000_000)["status"], "COLLECTOR_UNAVAILABLE")

    def test_healthy_zero_counters_can_complete_warmup(self):
        for second in range(31):
            for source in self.gate.sources:
                report = self.report(source, second)
                report["metrics_summary"]["events_observed"] = 0
                self.gate.observe(source, report, received_at_ns=second * 1_000_000_000)
        self.assertEqual(self.gate.inspect(30_000_000_000)["status"], "READY")

    def test_boolean_counters_are_rejected(self):
        report = self.report("ebpf", 0)
        report["metrics_summary"]["drops"] = False
        self.gate.observe("ebpf", report, received_at_ns=0)
        self.assertTrue(any("integers" in error for error in self.gate.inspect(0)["errors"]))

    def test_relaxed_timeout_is_not_accepted(self):
        with self.assertRaises(ValueError):
            HeartbeatReadinessGate("domain", heartbeat_interval_sec=1, timeout_sec=3)