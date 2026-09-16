import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from nwdaf_research.api.app import create_app


class ApiSecurityTests(unittest.TestCase):
    def setUp(self):
        raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
        self.audit_file = tempfile.NamedTemporaryFile(delete=False)
        self.audit_file.close()
        self.client = TestClient(create_app(raw_root, self.audit_file.name))
        self.payload = {
            "decisionId": "dec-security-1",
            "targetNF": "SMF",
            "target": {"supi": "imsi-security"},
            "action": "rate_limit",
            "duration": 30,
            "reason": "resource_exhaustion",
            "confidence": 0.95,
        }

    def tearDown(self):
        os.unlink(self.audit_file.name)

    def test_request_id_is_echoed_and_audit_is_written(self):
        response = self.client.post(
            "/security/v1/mitigation",
            headers={"X-Request-ID": "req-test-1"},
            json=self.payload,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Request-ID"], "req-test-1")
        content = Path(self.audit_file.name).read_text(encoding="utf-8")
        self.assertIn("req-test-1", content)
        self.assertIn("dec-security-1", content)

    def test_replayed_decision_is_rejected(self):
        first = self.client.post("/security/v1/mitigation", json=self.payload)
        replay = self.client.post("/security/v1/mitigation", json=self.payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 409)

    def test_configured_api_key_is_required(self):
        original = os.environ.get("NWDAF_API_KEY")
        os.environ["NWDAF_API_KEY"] = "test-key"
        try:
            unauthorized = self.client.post(
                "/security/v1/mitigation", json=self.payload
            )
            authorized = self.client.post(
                "/security/v1/mitigation",
                headers={"X-API-Key": "test-key"},
                json={**self.payload, "decisionId": "dec-security-2"},
            )
            self.assertEqual(unauthorized.status_code, 401)
            self.assertEqual(authorized.status_code, 200)
        finally:
            if original is None:
                os.environ.pop("NWDAF_API_KEY", None)
            else:
                os.environ["NWDAF_API_KEY"] = original


if __name__ == "__main__":
    unittest.main()