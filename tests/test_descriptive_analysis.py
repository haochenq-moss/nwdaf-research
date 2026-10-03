import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_benign_control import REGISTERED, benign_capture
from test_passive_campaign import valid_capture
from nwdaf_research.live.benign_control import PLAN_SHA256, run_pair
from nwdaf_research.live.descriptive_analysis import analyze_held_out


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "configs/benign_control_analysis_lock_v1.json"
AUTH = ROOT / "evaluation/descriptive_unblinding_authorization_20261003.json"


class DescriptiveAnalysisTests(unittest.TestCase):
    def test_verified_pair_recomputed_and_tampered_delta_invalidated(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            permission = root / "collection-permission.json"
            permission.write_text(json.dumps({
                "schema_version": "benign-held-out-authorization-v1", "plan_sha256": PLAN_SHA256,
                "registered_nf_instance_id": REGISTERED, "allowed_pair_ids": [5],
                "held_out_collection_authorized": True, "inference_authorized": False,
                "model_deployment_authorized": False, "network_enforcement_authorized": False,
                "response_scope": "operator_alert_only",
            }))
            def execute(command, **kwargs):
                return SimpleNamespace(stdout=json.dumps(
                    benign_capture() if "BENIGN_CONDITION =" in command[-1] else valid_capture()
                ))
            pair = root / "benign-control-held-out-pair05-20261003"
            run_pair(pair, pair_id=5, registered_nf_instance_id=REGISTERED, execute_benign=True,
                     authorization_path=permission, execute=execute)
            before = {path: path.read_bytes() for path in pair.rglob("*") if path.is_file()}
            result = analyze_held_out(root, lock_path=LOCK, authorization_path=AUTH)
            self.assertEqual(result["verified_pair_count"], 1)
            self.assertEqual(result["primary_endpoint_summary"]["zero"], 1)
            self.assertEqual(result["pairs"][0]["endpoint"], 0)
            self.assertEqual(len(result["implementation_strata"]), 1)
            self.assertFalse(result["inference_performed"])
            self.assertEqual(before, {path: path.read_bytes() for path in pair.rglob("*") if path.is_file()})
            path = pair / "pair_summary.json"
            summary = json.loads(path.read_text())
            summary["middle_sbi_event_count_delta"] = 999
            path.write_text(json.dumps(summary))
            result = analyze_held_out(root, lock_path=LOCK, authorization_path=AUTH)
            self.assertEqual(result["verified_pair_count"], 0)
            self.assertIsNone(result["pairs"][0]["endpoint"])

    def test_missing_pairs_retained_with_null_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            report = analyze_held_out(directory, lock_path=LOCK, authorization_path=AUTH)
        self.assertEqual(report["planned_pair_count"], 8)
        self.assertEqual(report["invalid_pair_count"], 8)
        self.assertEqual([row["pair_id"] for row in report["pairs"]], list(range(5, 13)))
        self.assertTrue(all(row["endpoint"] is None for row in report["pairs"]))
        self.assertIsNone(report["primary_endpoint_summary"]["median"])

    def test_no_model_or_threshold_authorization_allowed(self):
        auth = json.loads(AUTH.read_text())
        auth["inference_authorized"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "authorization.json"
            path.write_text(json.dumps(auth))
            with patch("nwdaf_research.live.descriptive_analysis.prepare_pair_review") as review:
                with self.assertRaisesRegex(ValueError, "only descriptive"):
                    analyze_held_out(directory, lock_path=LOCK, authorization_path=path)
                review.assert_not_called()

    def test_changed_lock_refused_before_pair_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.json"
            path.write_text("{}")
            with patch("nwdaf_research.live.descriptive_analysis.prepare_pair_review") as review:
                with self.assertRaisesRegex(ValueError, "lock changed"):
                    analyze_held_out(directory, lock_path=path, authorization_path=AUTH)
                review.assert_not_called()