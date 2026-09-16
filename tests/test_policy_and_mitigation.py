import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from nwdaf_research.adapters.mock_nf import MockNFAdapter
from nwdaf_research.api.app import create_app
from nwdaf_research.policy.engine import PolicyEngine


class PolicyEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = PolicyEngine()
        self.arguments = {
            "decision_id": "dec-1",
            "target_nf": "SMF",
            "target": {"supi": "imsi-1"},
            "action": "rate_limit",
            "duration": 60,
            "reason": "resource_exhaustion",
            "confidence": 0.95,
        }

    def test_allows_bounded_action(self):
        self.assertTrue(self.engine.evaluate(**self.arguments).allowed)

    def test_rejects_unsafe_inputs(self):
        cases = [
            {"action": "arbitrary_command"},
            {"target_nf": "UPF"},
            {"target": {}},
            {"confidence": 0.2},
            {"duration": 61},
        ]
        for override in cases:
            with self.subTest(override=override):
                arguments = {**self.arguments, **override}
                self.assertFalse(self.engine.evaluate(**arguments).allowed)

    def test_loads_external_policy_configuration(self):
        config_path = Path(__file__).resolve().parents[1] / "configs" / "policy.yaml"
        engine = PolicyEngine.from_yaml(config_path)
        self.assertTrue(engine.evaluate(**self.arguments).allowed)
        self.assertEqual(engine.actions["rate_limit"]["max_duration"], 60)


class MockNFAdapterTests(unittest.TestCase):
    def test_adapter_records_reaction_without_command_execution(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            decision_id="dec-2",
            target_nf="SMF",
            target={"supi": "imsi-2"},
            action="rate_limit",
            duration=30,
            reason="test",
            confidence=0.9,
        )
        adapter = MockNFAdapter()
        reaction = adapter.execute(decision)
        self.assertEqual(reaction["status"], "applied")
        self.assertEqual(len(adapter.nfs["SMF"].reactions), 1)


class MitigationApiTests(unittest.TestCase):
    def setUp(self):
        raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
        self.client = TestClient(create_app(raw_root))
        self.payload = {
            "decisionId": "dec-3",
            "targetNF": "SMF",
            "target": {"supi": "imsi-3"},
            "action": "rate_limit",
            "duration": 30,
            "reason": "resource_exhaustion",
            "confidence": 0.95,
        }

    def test_accepted_mitigation(self):
        response = self.client.post("/security/v1/mitigation", json=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "accepted")

    def test_rejected_mitigation_is_4xx(self):
        self.payload["action"] = "arbitrary_command"
        response = self.client.post("/security/v1/mitigation", json=self.payload)
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()