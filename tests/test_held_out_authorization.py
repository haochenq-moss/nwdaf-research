import json
import importlib.util
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_benign_control import REGISTERED, benign_capture
from test_passive_campaign import REPOSITORY, valid_capture
from nwdaf_research.live.benign_control import PLAN_SHA256, run_pair, validate_held_out_authorization


class HeldOutAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=REPOSITORY)
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "permission.json"
        self.authorization = {
            "schema_version": "benign-held-out-authorization-v1", "plan_sha256": PLAN_SHA256,
            "registered_nf_instance_id": REGISTERED, "allowed_pair_ids": [5],
            "held_out_collection_authorized": True, "inference_authorized": False,
            "model_deployment_authorized": False, "network_enforcement_authorized": False,
            "response_scope": "operator_alert_only",
        }
        self.path.write_text(json.dumps(self.authorization))

    def test_permission_bound_to_plan_pair_and_target(self):
        result = validate_held_out_authorization(self.path, pair_id=5, registered=REGISTERED)
        self.assertEqual(len(result["authorization_sha256"]), 64)
        for pair_id, registered in ((6, REGISTERED), (5, "wrong")):
            with self.assertRaises(ValueError):
                validate_held_out_authorization(self.path, pair_id=pair_id, registered=registered)

    def test_broad_model_or_enforcement_permission_is_refused(self):
        for field in ("inference_authorized", "model_deployment_authorized", "network_enforcement_authorized"):
            document = {**self.authorization, field: True}
            self.path.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                validate_held_out_authorization(self.path, pair_id=5, registered=REGISTERED)

    def test_missing_permission_stops_before_remote_or_pair_writes(self):
        execute = Mock()
        destination = Path(self.directory.name) / "pair"
        with self.assertRaisesRegex(ValueError, "scoped authorization"):
            run_pair(destination, pair_id=5, registered_nf_instance_id=REGISTERED,
                     execute_benign=True, execute=execute)
        execute.assert_not_called()
        self.assertFalse(destination.exists())

    def test_authorized_pair_has_held_out_group_and_permission_hash(self):
        def execute(command, **kwargs):
            capture = benign_capture() if "BENIGN_CONDITION =" in command[-1] else valid_capture()
            return SimpleNamespace(stdout=json.dumps(capture))
        result = run_pair(Path(self.directory.name) / "pair", pair_id=5,
                          registered_nf_instance_id=REGISTERED, execute_benign=True,
                          authorization_path=self.path, execute=execute)
        self.assertEqual(result["split"], "held_out")
        self.assertEqual(result["group"], "held_out-pair-05")
        self.assertEqual(result["condition_order"], ["passive", "benign_nrf"])
        self.assertEqual(result["status"], "READY")
        self.assertFalse(result["inference_performed"])

    def test_cli_withholds_held_out_counts_and_passes_permission(self):
        path = REPOSITORY / "scripts" / "run_benign_control_pair.py"
        spec = importlib.util.spec_from_file_location("held_out_cli", path)
        assert spec is not None and spec.loader is not None
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        summary = {"status": "READY", "authorization_sha256": "a" * 64,
                   "middle_sbi_event_count_delta": 999,
                   "outcomes": {"passive": {"status": "READY", "features": {"sbi_event_count": 999}}}}
        with patch.object(cli, "run_pair", return_value=summary) as runner, redirect_stdout(StringIO()) as output:
            self.assertEqual(cli.main([
                "--execute-benign", "--pair-id", "5", "--pair-dir", "new-pair",
                "--registered-nf-instance-id", REGISTERED, "--authorization", str(self.path),
            ]), 0)
        self.assertEqual(runner.call_args.kwargs["authorization_path"], str(self.path))
        report = json.loads(output.getvalue())
        self.assertTrue(report["results_withheld"])
        self.assertNotIn("middle_sbi_event_count_delta", report)
        self.assertNotIn("999", output.getvalue())