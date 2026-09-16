import unittest
from pathlib import Path

from nwdaf_research.adapters.mock_nf import MockNFAdapter
from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer
from nwdaf_research.loop.controller import ClosedLoopController
from nwdaf_research.loop.verification import ResponseVerifier
from nwdaf_research.policy.engine import PolicyEngine


class ClosedLoopTests(unittest.TestCase):
    def setUp(self):
        raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
        self.controller = ClosedLoopController(
            NWDAFResearchAnalyzer(raw_root), PolicyEngine(), MockNFAdapter()
        )

    def test_loop_records_reaction_and_measured_verification(self):
        event = self.controller.run(
            run_id="R00001",
            decision_id="dec-loop-1",
            target_nf="SMF",
            target={"supi": "imsi-1"},
            action="rate_limit",
            reason="resource_exhaustion",
            observation={"process_event_rate": 42, "service_latency": 0.4},
            after_observe=lambda: {"process_event_rate": 10, "service_latency": 0.2},
            duration=30,
        )
        self.assertEqual(event["response"]["status"], "applied")
        self.assertEqual(event["verification"]["status"], "measured")
        self.assertIn("service_latency_change", event["verification"]["available_metrics"])

    def test_loop_marks_missing_after_observation_unavailable(self):
        event = self.controller.run(
            run_id="R00001",
            decision_id="dec-loop-2",
            target_nf="SMF",
            target={"supi": "imsi-1"},
            action="rate_limit",
            reason="resource_exhaustion",
            observation={"process_event_rate": 42},
            duration=30,
        )
        self.assertEqual(event["verification"]["status"], "unavailable")

    def test_normal_prediction_does_not_trigger_nf_action(self):
        observation = self.controller.analytics.features_for_run("R00001")
        event = self.controller.run(
            run_id="R00001",
            decision_id="dec-loop-normal",
            target_nf="SMF",
            target={"supi": "imsi-1"},
            action="rate_limit",
            reason="not_used_for_normal_observation",
            observation=observation,
            duration=30,
        )
        self.assertEqual(event["detection"]["predicted_label"], "NORMAL")
        self.assertEqual(event["response"]["status"], "rejected")
        self.assertEqual(len(self.controller.adapter.nfs["SMF"].reactions), 0)


class ResponseVerifierTests(unittest.TestCase):
    def test_only_common_measured_values_are_compared(self):
        result = ResponseVerifier().verify(
            before={"service_latency": 0.4},
            after={"service_latency": 0.2},
            anomaly_score_before=0.9,
            anomaly_score_after=0.6,
        )
        self.assertEqual(result["available_metrics"]["service_latency_change"], -0.2)
        self.assertAlmostEqual(result["available_metrics"]["anomaly_score_change"], -0.3)


if __name__ == "__main__":
    unittest.main()