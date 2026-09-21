import tempfile
import unittest
from pathlib import Path

from nwdaf_research.architecture import ADRFStore, DCCF, MFAFRegistry, SecIRCompiler, VFLReporter
from nwdaf_research.policy.engine import PolicyEngine


class ArchitectureModuleTests(unittest.TestCase):
    def test_dccf_normalizes_and_correlates_events(self):
        events = DCCF().normalize([{"event_time": "t1", "nf_type": "SMF"}], source="sbi", run_id="R1")
        window = DCCF().correlate(events, window_id="w1", start="t0", end="t2", context={"slice": "A"})
        self.assertEqual(window.events[0].source, "sbi")
        self.assertEqual(window.context["slice"], "A")

    def test_dccf_collects_run_directory(self):
        root = Path(__file__).resolve().parents[1] / "data" / "raw" / "raw" / "R00001"
        window = DCCF().collect_run(root)
        self.assertEqual(window.window_id, "R00001")
        self.assertIn("linux", window.context["sources"])

    def test_mfaf_registers_model_manifest(self):
        registry = MFAFRegistry()
        record = registry.register(Path(__file__).resolve().parents[1] / "models" / "rf-v1")
        self.assertEqual(record.version, "rf-v1")
        self.assertEqual(registry.activate("random_forest", "rf-v1"), record)

    def test_adrf_persists_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ADRFStore(Path(directory) / "adrf.sqlite3")
            store.put("r1", {"type": "analytics", "classification": "anomaly"})
            self.assertEqual(store.get("r1")["classification"], "anomaly")
            self.assertEqual(len(store.list("analytics")), 1)

    def test_secir_compiles_only_allowed_decisions(self):
        decision = PolicyEngine().evaluate(
            decision_id="w1", target_nf="SMF", target={"interface": "ueTun0"},
            action="rate_limit", duration=5, reason="test", confidence=0.95,
        )
        workflow = SecIRCompiler().compile(
            decision,
            evidence={"source": "test", "autonomous_response_eligible": True},
        )
        self.assertEqual(workflow.rollback_action, "restore_fq_codel")
        self.assertEqual(workflow.steps[0].operation, "apply_tc_rate_limit")
        self.assertEqual(workflow.as_dict()["steps"][0]["postconditions"], ["qdisc_is_tbf"])

    def test_secir_rejects_incomplete_evidence(self):
        decision = PolicyEngine().evaluate(
            decision_id="w2", target_nf="SMF", target={"interface": "ueTun0"},
            action="rate_limit", duration=5, reason="test", confidence=0.95,
        )
        with self.assertRaises(ValueError):
            SecIRCompiler().compile(decision)

    def test_vfl_creates_operational_report(self):
        report = VFLReporter().create(report_id="r1", lifecycle="detected", severity="high", confidence=0.9)
        self.assertEqual(report.lifecycle, "detected")
        self.assertEqual(VFLReporter().as_payload(report)["lifecycle"], "detected")


if __name__ == "__main__":
    unittest.main()