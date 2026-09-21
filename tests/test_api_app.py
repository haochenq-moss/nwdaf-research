import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from nwdaf_research.api.app import create_app


class AnalyticsApiTests(unittest.TestCase):
    def setUp(self):
        raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
        self.client = TestClient(create_app(raw_root))

    def test_security_analytics_returns_real_model_metadata(self):
        response = self.client.post(
            "/nnwdaf-analyticsinfo/v1/security-analytics",
            json={
                "analyticsId": "security-anomaly",
                "target": {"nf": "SMF", "supi": "imsi-208930000000001"},
                "timeWindow": {
                    "start": "2026-09-16T08:00:00Z",
                    "end": "2026-09-16T08:00:10Z",
                },
                "features": {"process_event_rate": 42, "socket_event_rate": 18},
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(body["result"]["classification"], {"normal", "anomaly"})
        self.assertEqual(body["model"]["name"], "random_forest")
        self.assertEqual(body["model"]["version"], "rf-v1")

    def test_architecture_status_exposes_module_boundaries(self):
        response = self.client.get("/architecture/v1/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["modules"]["DCCF"], "active")
        self.assertEqual(body["modules"]["NemoIR"], "reporting_only")

    def test_invalid_time_window_is_rejected(self):
        response = self.client.post(
            "/nnwdaf-analyticsinfo/v1/security-analytics",
            json={
                "analyticsId": "security-anomaly",
                "target": {"nf": "SMF"},
                "timeWindow": {
                    "start": "2026-09-16T08:00:10Z",
                    "end": "2026-09-16T08:00:00Z",
                },
                "features": {},
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_subscription_is_stored(self):
        payload = {
            "notificationUri": "http://nf-adapter:8080/nwdaf-notify",
            "analyticsId": "security-anomaly",
            "target": {"nf": "SMF"},
            "reportingInterval": 10,
        }
        created = self.client.post(
            "/nnwdaf-eventssubscription/v1/subscriptions", json=payload
        )
        self.assertEqual(created.status_code, 201)
        listed = self.client.get("/nnwdaf-eventssubscription/v1/subscriptions")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

    def test_notification_is_generated_for_latest_analytics_result(self):
        payload = {
            "notificationUri": "http://nf-adapter:8080/nwdaf-notify",
            "analyticsId": "security-anomaly",
            "target": {"nf": "SMF"},
            "reportingInterval": 10,
        }
        self.client.post("/nnwdaf-eventssubscription/v1/subscriptions", json=payload)
        analytics_response = self.client.post(
            "/nnwdaf-analyticsinfo/v1/security-analytics",
            json={
                "analyticsId": "security-anomaly",
                "target": {"nf": "SMF"},
                "timeWindow": {
                    "start": "2026-09-16T08:00:00Z",
                    "end": "2026-09-16T08:00:10Z",
                },
                "features": {"process_event_rate": 42},
            },
        )
        self.assertEqual(analytics_response.status_code, 200)
        notifications = self.client.post(
            "/nnwdaf-eventssubscription/v1/notifications?analytics_id=security-anomaly"
        )
        self.assertEqual(notifications.status_code, 200)
        self.assertEqual(len(notifications.json()), 1)
        self.assertEqual(notifications.json()[0]["analyticsId"], "security-anomaly")


if __name__ == "__main__":
    unittest.main()