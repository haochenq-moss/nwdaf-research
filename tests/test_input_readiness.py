import hashlib
import importlib.util
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path

from nwdaf_research.input_testing.readiness import inspect_campaign_readiness
from nwdaf_research.input_testing.records import InputCase, RunLabel, TestOutcome, write_jsonl


class CampaignReadinessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.campaign = Path(self.directory.name)
        self.cases = []
        self.outcomes = []
        self.labels = []
        for index, split in enumerate(("train", "held_out")):
            payload = f"input-{index}".encode()
            corpus_path = f"case-{index}.bin"
            (self.campaign / corpus_path).write_bytes(payload)
            self.cases.append(InputCase(
                f"case-{index}", "ordinary", "NAS GMM", hashlib.sha256(payload).hexdigest(),
                corpus_path, "a" * 40, trial_group=f"family-{index}",
            ))
            run_id = f"test-{index}"
            self.outcomes.append(TestOutcome(
                f"outcome-{index}", f"case-{index}", run_id,
                "2026-10-03T00:00:00Z", "2026-10-03T00:01:00Z", "rejected",
            ))
            self.labels.extend((RunLabel(run_id, "input_test", split),
                                RunLabel(f"normal-{index}", "normal", split)))
        self.write_records()
        for label in self.labels:
            run = self.campaign / "runs" / label.run_id
            (run / "linux").mkdir(parents=True)
            for filename in ("metadata.json", "ground_truth.json", "timeline.json"):
                (run / filename).write_text("{}", encoding="utf-8")
            (run / "linux" / "events.jsonl").write_text('{"load_1m": 0.1}\n', encoding="utf-8")

    def write_records(self):
        write_jsonl(self.campaign / "input_cases.jsonl", self.cases)
        write_jsonl(self.campaign / "outcomes.jsonl", self.outcomes)
        write_jsonl(self.campaign / "run_labels.jsonl", self.labels)

    def test_complete_structure_is_read_only_and_missing_network_is_not_zero(self):
        before = {path: path.read_bytes() for path in self.campaign.rglob("*") if path.is_file()}
        report = inspect_campaign_readiness(self.campaign)
        self.assertTrue(report["structurally_ready"], report["blockers"])
        self.assertIsNone(report["source_event_counts"]["test-0"]["pfcp"])
        after = {path: path.read_bytes() for path in self.campaign.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_missing_manifests_are_reported(self):
        (self.campaign / "outcomes.jsonl").unlink()
        report = inspect_campaign_readiness(self.campaign)
        self.assertFalse(report["structurally_ready"])
        self.assertTrue(any("Cannot read outcomes" in item for item in report["blockers"]))

    def test_missing_linux_and_normal_controls_block_readiness(self):
        (self.campaign / "runs" / "test-0" / "linux" / "events.jsonl").unlink()
        self.labels = [label for label in self.labels if label.label == "input_test"]
        self.write_records()
        blockers = inspect_campaign_readiness(self.campaign)["blockers"]
        self.assertTrue(any("Missing observed Linux" in item for item in blockers))
        self.assertTrue(any("Need normal" in item for item in blockers))

    def test_hash_mismatch_blocks_readiness(self):
        (self.campaign / "case-0.bin").write_bytes(b"changed")
        self.assertTrue(any("SHA-256 mismatch" in item for item in
                            inspect_campaign_readiness(self.campaign)["blockers"]))

    def test_identical_bytes_and_families_cannot_cross_splits(self):
        self.cases[1] = replace(self.cases[1], input_sha256=self.cases[0].input_sha256,
                                trial_group=self.cases[0].trial_group)
        (self.campaign / "case-1.bin").write_bytes((self.campaign / "case-0.bin").read_bytes())
        self.write_records()
        blockers = inspect_campaign_readiness(self.campaign)["blockers"]
        self.assertTrue(any("Cross-split leakage for input_sha256" in item for item in blockers))
        self.assertTrue(any("Cross-split leakage for trial_group" in item for item in blockers))

    def test_malformed_event_blocks_readiness(self):
        (self.campaign / "runs" / "test-0" / "linux" / "events.jsonl").write_text("[]\n")
        self.assertFalse(inspect_campaign_readiness(self.campaign)["structurally_ready"])

    def test_cli_exit_code_matches_readiness(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "check_input_campaign.py"
        spec = importlib.util.spec_from_file_location("check_input_campaign", script)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(module.main(["--campaign-dir", str(self.campaign)]), 0)
        self.assertIn('"structurally_ready": true', output.getvalue())
        (self.campaign / "outcomes.jsonl").unlink()
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(module.main(["--campaign-dir", str(self.campaign)]), 1)
        self.assertIn('"structurally_ready": false', output.getvalue())

    def test_corpus_symlink_cannot_escape_campaign(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "input.bin"
            target.write_bytes((self.campaign / "case-0.bin").read_bytes())
            (self.campaign / "case-0.bin").unlink()
            (self.campaign / "case-0.bin").symlink_to(target)
            blockers = inspect_campaign_readiness(self.campaign)["blockers"]
            self.assertTrue(any("Corpus escapes campaign" in item for item in blockers))


if __name__ == "__main__":
    unittest.main()