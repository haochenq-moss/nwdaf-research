import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from nwdaf_research.api.app import create_app


class RemoteAdapterApiTests(unittest.TestCase):
    def test_api_accepts_explicit_response_agent_configuration(self):
        raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
        with patch("nwdaf_research.api.app.HTTPNFAdapter") as adapter:
            adapter.return_value.execute.return_value = {
                "status": "accepted",
                "action": "alert_operator",
                "targetNF": "SMF",
            }
            client = TestClient(
                create_app(
                    raw_root,
                    response_agent_endpoint="http://127.0.0.1:9090",
                    response_agent_api_key="test-key",
                )
            )
            response = client.post(
                "/security/v1/mitigation",
                json={
                    "decisionId": "remote-1",
                    "targetNF": "SMF",
                    "target": {"supi": "imsi-1"},
                    "action": "alert_operator",
                    "reason": "test",
                    "confidence": 0.95,
                },
            )
            self.assertEqual(response.status_code, 200)
            adapter.return_value.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()