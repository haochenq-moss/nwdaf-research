import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from test_passive_campaign import valid_capture
from nwdaf_research.live.baseline_evidence import summarize_baseline_campaigns
from nwdaf_research.live.passive_campaign import run_campaign


class BaselineEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.campaign = Path(self.temp.name) / "campaign"
        run_campaign(self.campaign, execute=Mock(return_value=SimpleNamespace(stdout=json.dumps(valid_capture()))))

    def test_revalidates_all_windows_without_inference_or_label_promotion(self):
        before = {path: path.read_bytes() for path in self.campaign.rglob("*") if path.is_file()}
        result = summarize_baseline_campaigns([self.campaign])
        self.assertEqual(result["ready_window_count"], 3)
        self.assertEqual(len(result["feature_statistics"]), 16)
        self.assertFalse(result["evaluation_ready"])
        self.assertFalse(result["inference_performed"])
        self.assertEqual(result["campaigns"][0]["label_review"], "not_performed")
        self.assertEqual(result["campaigns"][0]["condition"], "passive")
        self.assertEqual(before, {path: path.read_bytes() for path in self.campaign.rglob("*") if path.is_file()})

    def test_changed_window_is_rejected(self):
        path = self.campaign / "windows" / "WBASE001" / "readiness.json"
        row = json.loads(path.read_text())
        row["features"]["sbi_event_count"] = 999
        path.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError, "disagrees"):
            summarize_baseline_campaigns([self.campaign])

    def test_duplicate_campaign_is_not_counted_as_independent_evidence(self):
        with self.assertRaisesRegex(ValueError, "duplicate campaign"):
            summarize_baseline_campaigns([self.campaign, self.campaign])

    def test_changed_manifest_identity_is_rejected(self):
        path = self.campaign / "manifest.json"
        row = json.loads(path.read_text())
        row["boot_id"] = "different"
        path.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError, "manifest identity"):
            summarize_baseline_campaigns([self.campaign])