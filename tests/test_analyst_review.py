import json
import importlib.util
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from test_benign_control import REGISTERED, benign_capture
from test_passive_campaign import REPOSITORY, valid_capture
from nwdaf_research.live.analyst_review import REVIEW_CHECKS, prepare_pair_review, validate_analyst_decision
from nwdaf_research.live.benign_control import run_pair


class AnalystReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=REPOSITORY)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "pair"
        def execute(command, **kwargs):
            capture = benign_capture() if "BENIGN_CONDITION =" in command[-1] else valid_capture()
            return SimpleNamespace(stdout=json.dumps(capture))
        run_pair(self.root, pair_id=1, registered_nf_instance_id=REGISTERED, execute_benign=True, execute=execute)

    def decision(self):
        return {
            "schema_version": "benign-pair-analyst-decision-v1",
            "packet_binding_sha256": prepare_pair_review(self.root)["packet_binding_sha256"],
            "reviewer_id": "synthetic-test-reviewer", "reviewed_at": "2026-10-03T00:00:00Z",
            "independence_declared": True, "decision": "approved", "rationale": "Synthetic test only",
            "checks": dict.fromkeys(REVIEW_CHECKS, True),
        }

    def test_packet_is_pending_hash_bound_and_read_only(self):
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        packet = prepare_pair_review(self.root)
        self.assertEqual(packet["review_status"], "PENDING")
        self.assertEqual(packet["label_review"], "not_performed")
        self.assertEqual(len(packet["artifact_sha256"]), 27)
        self.assertEqual(packet, prepare_pair_review(self.root))
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_valid_external_decision_does_not_authenticate_or_approve_model(self):
        result = validate_analyst_decision(self.root, self.decision())
        self.assertTrue(result["decision_structure_valid"])
        self.assertFalse(result["reviewer_identity_authenticated"])
        self.assertFalse(result["model_approved"])
        self.assertFalse(result["acquisition_labels_modified"])

    def test_stale_binding_and_incomplete_approval_rejected(self):
        for change in ({"packet_binding_sha256": "0" * 64}, {"independence_declared": False}, {"rationale": ""}):
            decision = self.decision()
            decision.update(change)
            with self.assertRaises(ValueError):
                validate_analyst_decision(self.root, decision)
        decision = self.decision()
        decision["checks"]["fixture_and_label_basis"] = False
        with self.assertRaisesRegex(ValueError, "approval requires"):
            validate_analyst_decision(self.root, decision)

    def test_saved_delta_tampering_rejected(self):
        path = self.root / "pair_summary.json"
        document = json.loads(path.read_text())
        document["middle_sbi_event_count_delta"] = 999
        path.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError, "delta disagrees"):
            prepare_pair_review(self.root)

    def test_inconclusive_review_can_record_unsatisfied_checks(self):
        decision = self.decision()
        decision["decision"] = "inconclusive"
        decision["checks"]["provenance_limitations"] = False
        self.assertEqual(validate_analyst_decision(self.root, decision)["decision"], "inconclusive")

    def test_cli_exports_only_pending_unsigned_review_and_refuses_overwrite(self):
        path = REPOSITORY / "scripts" / "prepare_benign_pair_review.py"
        spec = importlib.util.spec_from_file_location("prepare_benign_pair_review", path)
        assert spec is not None and spec.loader is not None
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        output = Path(self.directory.name) / "review"
        with redirect_stdout(StringIO()):
            cli.main(["--pair-dir", str(self.root), "--output-dir", str(output)])
        draft = json.loads((output / "analyst_decision.draft.json").read_text())
        self.assertEqual(json.loads((output / "review_packet.json").read_text())["review_status"], "PENDING")
        self.assertEqual(draft["reviewer_id"], "")
        self.assertFalse(draft["independence_declared"])
        with self.assertRaises(ValueError):
            validate_analyst_decision(self.root, draft)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            cli.main(["--pair-dir", str(self.root), "--output-dir", str(output)])

    def test_frozen_plan_tampering_rejected(self):
        (self.root / "frozen_plan.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "plan hash mismatch"):
            prepare_pair_review(self.root)