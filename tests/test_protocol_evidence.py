import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from nwdaf_research.input_testing.protocol_evidence import STAGES, inspect_case_evidence


class ProtocolEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.input = self.save("input.bin", b"synthetic identity fixture, not a NAS payload")
        self.support = self.save("observation.txt", b"synthetic observation only")
        self.manifest = {
            "schema_version": "fuzz-case-evidence-v1", "input_id": "case-1", "run_id": "run-1",
            "free5gc_commit": "a" * 40, "window_start": "2026-10-03T00:00:00Z",
            "window_end": "2026-10-03T00:00:10Z", "input": self.input, "stages": {},
        }
        for name in STAGES:
            record = {
                "input_id": "case-1", "run_id": "run-1", "free5gc_commit": "a" * 40,
                "input_sha256": self.input["sha256"], "evidence_refs": [self.support],
                "window_start": self.manifest["window_start"], "window_end": self.manifest["window_end"],
                "observed_outcome": "synthetic fixture", "reviewer_id": "fixture-reviewer",
                "reviewed_at": "2026-10-03T00:01:00Z", "decision": "approved", "rationale": "test fixture only",
            }
            self.manifest["stages"][name] = self.save(name + ".json", json.dumps(record).encode())
        self.write_manifest()

    def save(self, name, payload):
        (self.root / name).write_bytes(payload)
        return {"path": name, "sha256": hashlib.sha256(payload).hexdigest()}

    def write_manifest(self):
        (self.root / "case_evidence.json").write_text(json.dumps(self.manifest))

    def test_complete_references_do_not_claim_detection_or_protocol_correctness(self):
        report = inspect_case_evidence(self.root)
        self.assertEqual(report["evidence_chain_status"], "REFERENCES_COMPLETE")
        for name in ("protocol_correctness_established", "fuzz_triggered_detection_demonstrated", "actionable"):
            self.assertFalse(report[name])

    def test_missing_cleanup_blocks(self):
        del self.manifest["stages"]["cleanup_review"]
        self.write_manifest()
        self.assertEqual(inspect_case_evidence(self.root)["stages"]["cleanup_review"]["status"], "MISSING")

    def test_tampered_input_and_evidence_block(self):
        (self.root / "input.bin").write_bytes(b"changed")
        (self.root / "observation.txt").write_bytes(b"changed")
        report = inspect_case_evidence(self.root)
        self.assertEqual(report["input_status"], "UNVERIFIED")
        self.assertEqual(report["evidence_chain_status"], "INCOMPLETE")

    def test_telemetry_must_bracket_network_window(self):
        path = self.root / "telemetry_bundle.json"
        record = json.loads(path.read_text())
        record["window_start"] = "2026-10-03T00:00:05Z"
        self.manifest["stages"]["telemetry_bundle"] = self.save(path.name, json.dumps(record).encode())
        self.write_manifest()
        self.assertIn("bracket", inspect_case_evidence(self.root)["stages"]["telemetry_bundle"]["issue"])

    def test_context_identity_must_match(self):
        path = self.root / "protocol_state_review.json"
        record = json.loads(path.read_text())
        record["run_id"] = "different-run"
        self.manifest["stages"]["protocol_state_review"] = self.save(path.name, json.dumps(record).encode())
        self.write_manifest()
        self.assertEqual(inspect_case_evidence(self.root)["stages"]["protocol_state_review"]["status"], "UNVERIFIED")