import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from nwdaf_research.input_testing.anomaly_dataset import FEATURES, evaluate_anomaly_dataset, load_anomaly_dataset
from nwdaf_research.input_testing.protocol_evidence import STAGES
from nwdaf_research.live.telemetry_window import BASELINE_CONTRACT, TelemetryWindow


class AnomalyDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps({
            "schema_version": "fuzz-anomaly-analysis-plan-v1", "contract": BASELINE_CONTRACT,
            "feature_names": list(FEATURES), "model": "random_forest_200_seed42", "threshold": 0.5,
            "frozen_at": "2026-10-03T00:00:00Z",
            "frozen": True,
            "collection_semantics": "observation_time_cursor_reads_excluding_preexisting_history",
        }))
        self.runs = []
        for split in ("train", "held_out"):
            for label in ("normal", "expected_rejection", "anomalous"):
                self.create_bundle(split, label)
        self.dataset = self.root / "dataset.json"
        self.write_dataset()

    def reference(self, root, name, value):
        payload = value if isinstance(value, bytes) else json.dumps(value).encode()
        (root / name).write_bytes(payload)
        return {"path": name, "sha256": hashlib.sha256(payload).hexdigest()}

    def create_bundle(self, split, label):
        identity = split + "-" + label
        root = self.root / identity
        root.mkdir()
        start = datetime(2026, 10, 1 if split == "train" else 4, tzinfo=timezone.utc)
        end = start + timedelta(seconds=2)
        input_ref = self.reference(root, "input.bin", identity.encode())
        support = self.reference(root, "observation.txt", b"synthetic observation, not NAS or live evidence")
        manifest = {"schema_version": "fuzz-case-evidence-v1", "input_id": identity, "run_id": identity,
                    "free5gc_commit": "a" * 40, "window_start": start.isoformat(), "window_end": end.isoformat(),
                    "input": input_ref, "stages": {}}
        stream = []
        window = TelemetryWindow(start, contract=BASELINE_CONTRACT)
        for offset in range(3):
            timestamp = (start + timedelta(seconds=offset)).isoformat()
            counters = dict.fromkeys(window.counter_sources, 0)
            counters["linux_event_count"] = offset
            stream.append({
                "type": "snapshot", "run_id": identity, "input_sha256": input_ref["sha256"],
                "observed_at": timestamp, "counters": counters,
                "linux_sample": {"load_1m": 10.0 if label == "anomalous" else 0.1,
                                 "memory_total": 100, "memory_available": 40},
                "collectors": {source: {"heartbeat_at": timestamp, "observed_through": timestamp,
                                        "collector_healthy": True, "telemetry_source_synced": True}
                               for source in window.primary_sources},
            })
        stream.append({"type": "seal", "run_id": identity, "input_sha256": input_ref["sha256"], "observed_at": end.isoformat()})
        snapshots = self.reference(root, "snapshots.jsonl", b"".join(json.dumps(row).encode() + b"\n" for row in stream))
        for stage in STAGES:
            record = {"input_id": identity, "run_id": identity, "free5gc_commit": "a" * 40,
                      "input_sha256": input_ref["sha256"], "window_start": start.isoformat(), "window_end": end.isoformat(),
                      "observed_outcome": "synthetic externally labelled fixture", "evidence_refs": [support],
                      "reviewer_id": "fixture-reviewer", "reviewed_at": (end + timedelta(minutes=1)).isoformat(),
                      "decision": "approved", "rationale": "synthetic unit test only"}
            if stage == "telemetry_bundle":
                record.update(contract=BASELINE_CONTRACT, snapshots_ref=snapshots,
                              clock_domain="synthetic-host/boot/CLOCK_MONOTONIC",
                              evidence_refs=[support, snapshots],
                              collection_semantics="observation_time_cursor_reads_excluding_preexisting_history")
            if stage == "analyst_decision":
                record.update(outcome_label=label, independence_declared=True, label_basis="independent_observed_behavior")
            manifest["stages"][stage] = self.reference(root, stage + ".json", record)
        (root / "case_evidence.json").write_text(json.dumps(manifest))
        self.runs.append({"bundle_path": identity, "split": split, "unseen_declared": split == "held_out",
                          "input_family": identity, "episode_group": identity})

    def write_dataset(self):
        self.dataset.write_text(json.dumps({"schema_version": "fuzz-anomaly-dataset-v1",
                                           "analysis_plan_sha256": hashlib.sha256(self.plan.read_bytes()).hexdigest(),
                                           "runs": self.runs}))

    def rewrite_record(self, bundle, stage, change):
        root = self.root / bundle
        manifest = json.loads((root / "case_evidence.json").read_text())
        record = json.loads((root / (stage + ".json")).read_text())
        change(record)
        manifest["stages"][stage] = self.reference(root, stage + ".json", record)
        (root / "case_evidence.json").write_text(json.dumps(manifest))

    def test_real_training_on_synthetic_fixture_and_separate_control_metrics(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        report = evaluate_anomaly_dataset(self.dataset, self.plan)
        self.assertEqual(report["held_out_run_count"], 3)
        self.assertEqual(len(report["feature_names"]), 16)
        self.assertEqual(set(report["control_metrics"]), {"normal", "expected_rejection"})
        self.assertIn("precision", report["metrics"])
        self.assertFalse(report["model_deployment_approved"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_family_leakage_rejected_before_fit(self):
        self.runs[-1]["input_family"] = self.runs[0]["input_family"]
        self.write_dataset()
        with patch("nwdaf_research.input_testing.anomaly_dataset.RandomForestClassifier") as model:
            with self.assertRaisesRegex(ValueError, "cross-split leakage"):
                evaluate_anomaly_dataset(self.dataset, self.plan)
            model.assert_not_called()

    def test_previously_seen_held_out_refused(self):
        self.runs[-1]["unseen_declared"] = False
        self.write_dataset()
        with self.assertRaisesRegex(ValueError, "newly collected"):
            load_anomaly_dataset(self.dataset, self.plan)

    def test_exposure_label_is_not_anomaly_ground_truth(self):
        self.rewrite_record("held_out-anomalous", "analyst_decision", lambda row: row.update(outcome_label="input_test"))
        with self.assertRaisesRegex(ValueError, "independent outcome"):
            load_anomaly_dataset(self.dataset, self.plan)

    def test_missing_source_is_not_zero_imputed(self):
        bundle = self.root / "train-normal"
        rows = [json.loads(line) for line in (bundle / "snapshots.jsonl").read_text().splitlines()]
        del rows[1]["collectors"]["pfcp"]
        new_ref = self.reference(bundle, "snapshots.jsonl", b"".join(json.dumps(row).encode() + b"\n" for row in rows))
        def change(record):
            record["snapshots_ref"] = new_ref
            record["evidence_refs"][-1] = new_ref
        self.rewrite_record("train-normal", "telemetry_bundle", change)
        with self.assertRaisesRegex(ValueError, "not ready"):
            load_anomaly_dataset(self.dataset, self.plan)

    def test_case_hash_tampering_blocks(self):
        (self.root / "train-normal" / "input.bin").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "incomplete case evidence"):
            load_anomaly_dataset(self.dataset, self.plan)

    def test_plan_is_hash_bound_and_must_be_frozen(self):
        plan = json.loads(self.plan.read_text())
        plan["frozen"] = False
        self.plan.write_text(json.dumps(plan))
        self.write_dataset()
        with self.assertRaisesRegex(ValueError, "explicitly frozen"):
            load_anomaly_dataset(self.dataset, self.plan)
        plan["frozen"] = True
        self.plan.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, "exact frozen analysis plan"):
            load_anomaly_dataset(self.dataset, self.plan)

    def test_post_collection_freeze_cannot_create_unseen_data(self):
        plan = json.loads(self.plan.read_text())
        plan["frozen_at"] = "2026-10-05T00:00:00Z"
        self.plan.write_text(json.dumps(plan))
        self.write_dataset()
        with self.assertRaisesRegex(ValueError, "newly collected"):
            load_anomaly_dataset(self.dataset, self.plan)