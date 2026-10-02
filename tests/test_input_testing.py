import json
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nwdaf_research.input_testing import (
    InputCase,
    RunLabel,
    TestOutcome,
    compare_input_outcomes,
    capture_normal_baseline,
    capture_live_observation,
    evaluate_campaign,
    evaluate_run_detection,
    features_for_runs,
    read_jsonl,
    run_nrf_discovery_case,
    materialize_input_test_runs,
    assign_input_test_splits,
    validate_campaign,
    write_jsonl,
)
from nwdaf_research.preprocessing.features import RunFeatureBuilder
from nwdaf_research.input_testing.nrf_discovery import (
    _remote_probe,
    _remote_python_source,
    validate_candidate_path,
)
from nwdaf_research.input_testing.normal_baseline import REMOTE_BASELINE
from nwdaf_research.input_testing.fuzz_provenance import (
    AnalystReview,
    CoverageEvidence,
    FuzzExecution,
    FuzzRunProvenance,
    ReproductionEvidence,
    SecurityReview,
)
from nwdaf_research.input_testing.trial_generation import build_candidate_rows


class InputTestingRecordTests(unittest.TestCase):
    def test_fuzz_provenance_keeps_execution_coverage_and_reviews_distinct(self):
        record = FuzzRunProvenance(
            run_id="FZ0001",
            campaign_id="nas-parser-pilot",
            input_id="seed-001",
            corpus_path="corpus/llm/seed-001.bin",
            input_sha256="a" * 64,
            input_size_bytes=3,
            input_source="llm_suggested",
            generator_model="qwen2.5-coder:3b",
            free5gc_commit="4" * 40,
            component="free5gc NAS",
            function="message.ParseGMM",
            harness_path="test/nasTestpacket/fuzz_parse_test.go",
            harness_sha256="b" * 64,
            fuzz_engine="go-native",
            go_version="go1.26.2",
            platform="linux/amd64",
            config_sha256="c" * 64,
            seed=42,
            max_duration_seconds=30,
            max_input_bytes=4096,
            started_at="2026-10-01T12:00:00Z",
            ended_at="2026-10-01T12:00:02Z",
            execution=FuzzExecution("crash", 2, "SIGABRT", 30, crash_signature="sig-abrt"),
            coverage=CoverageEvidence("collected", 10, 12, 2, "coverage/seed-001.json"),
            reproduction=ReproductionEvidence("not_attempted", None, None),
            bug_review=AnalystReview("unreviewed", None, ()),
            security_review=SecurityReview("not_assessed", None, ()),
        )
        serialized = record.as_dict()
        self.assertEqual(serialized["execution"]["status"], "crash")
        self.assertEqual(serialized["coverage"]["delta"], 2)
        self.assertEqual(serialized["reproduction"]["status"], "not_attempted")
        self.assertEqual(serialized["bugReview"]["status"], "unreviewed")
        self.assertEqual(serialized["securityReview"]["status"], "not_assessed")
        self.assertEqual(serialized["input"]["sizeBytes"], 3)
        self.assertEqual(serialized["input"]["corpusPath"], "corpus/llm/seed-001.bin")
        schema_path = Path(__file__).resolve().parents[1] / "schemas" / "fuzz-run.schema.json"
        schema_properties = json.loads(schema_path.read_text(encoding="utf-8"))["properties"]
        self.assertTrue(set(schema_properties).issuperset(serialized))
        for section, definition in schema_properties.items():
            if definition.get("type") == "object":
                self.assertTrue(set(definition.get("required", ())).issubset(serialized[section]))
                self.assertTrue(set(serialized[section]).issubset(definition["properties"]))

    def test_fuzz_provenance_rejects_vulnerability_without_confirmed_bug_review(self):
        with self.assertRaisesRegex(ValueError, "underlying bug"):
            FuzzRunProvenance(
                run_id="FZ0002", campaign_id="pilot", input_id="seed-002",
                corpus_path="corpus/ordinary/seed-002.bin",
                input_sha256="a" * 64, input_size_bytes=1, input_source="ordinary",
                generator_model=None, free5gc_commit="4" * 40, component="NAS",
                function="message.ParseGMM", harness_path="fuzz_parse_test.go",
                harness_sha256="b" * 64, fuzz_engine="go-native", go_version="go1.26.2",
                platform="linux/amd64", config_sha256="c" * 64, seed=1,
                max_duration_seconds=5, max_input_bytes=100,
                started_at="2026-10-01T12:00:00Z", ended_at="2026-10-01T12:00:01Z",
                execution=FuzzExecution("crash", 1, "SIGABRT", 5),
                coverage=CoverageEvidence("unavailable", None, None, None, None),
                reproduction=ReproductionEvidence("not_attempted", None, None),
                bug_review=AnalystReview("unreviewed", None, ()),
                security_review=SecurityReview("confirmed_vulnerability", "analyst", ("evidence-1",)),
            )

    def test_fuzz_provenance_requires_reproduction_before_confirmed_bug(self):
        with self.assertRaisesRegex(ValueError, "behavior is reproduced"):
            FuzzRunProvenance(
                run_id="FZ0003", campaign_id="pilot", input_id="seed-003",
                corpus_path="corpus/ordinary/seed-003.bin",
                input_sha256="a" * 64, input_size_bytes=1, input_source="ordinary",
                generator_model=None, free5gc_commit="4" * 40, component="NAS",
                function="message.ParseGMM", harness_path="fuzz_parse_test.go",
                harness_sha256="b" * 64, fuzz_engine="go-native", go_version="go1.26.2",
                platform="linux/amd64", config_sha256="c" * 64, seed=1,
                max_duration_seconds=5, max_input_bytes=100,
                started_at="2026-10-01T12:00:00Z", ended_at="2026-10-01T12:00:01Z",
                execution=FuzzExecution("crash", 1, "SIGABRT", 5),
                coverage=CoverageEvidence("unavailable", None, None, None, None),
                reproduction=ReproductionEvidence("not_attempted", None, None),
                bug_review=AnalystReview("confirmed_bug", "analyst", ("evidence-1",)),
                security_review=SecurityReview("not_assessed", None, ()),
            )

    def test_fuzz_schema_keeps_result_dimensions_separate_and_gates_vulnerability(self):
        schema_path = Path(__file__).resolve().parents[1] / "schemas" / "fuzz-run.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        properties = schema["properties"]
        self.assertEqual(
            properties["execution"]["properties"]["status"]["enum"],
            ["completed", "crash", "hang", "timeout", "error"],
        )
        self.assertEqual(
            properties["reproduction"]["properties"]["status"]["enum"][0],
            "not_attempted",
        )
        self.assertIn("bugReview", properties)
        self.assertIn("securityReview", properties)
        self.assertTrue(any("confirmed_vulnerability" in json.dumps(rule) for rule in schema["allOf"]))

    def test_crash_and_hang_execution_have_distinct_evidence_requirements(self):
        with self.assertRaisesRegex(ValueError, "signal or crash signature"):
            FuzzExecution("crash", 1, None, 10)
        with self.assertRaisesRegex(ValueError, "reproducible artifact"):
            FuzzExecution("hang", None, None, 10)

    def test_model_trial_rows_have_distinct_replicates_and_remain_unrun(self):
        rows = build_candidate_rows("llama3.2:3b", [2, 6], repeats=2, batch_index=2)
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({row["candidate_id"] for row in rows}), 4)
        self.assertEqual({row["execution_status"] for row in rows}, {"not_run"})
        self.assertEqual({row["model"] for row in rows}, {"llama3.2:3b"})
        self.assertEqual({row["replicate_index"] for row in rows}, {1, 2})
        self.assertEqual(rows[0]["trial_group"], "llama3-2-3b-b02-template-2")
        first_batch = build_candidate_rows("llama3.2:3b", [2], repeats=2, batch_index=1)
        self.assertTrue(set(row["candidate_id"] for row in first_batch).isdisjoint(
            row["candidate_id"] for row in rows
        ))
    def test_candidate_path_allowlist_accepts_read_only_template_and_rejects_mutation(self):
        path = "/nnrf-disc/v1/nf-instances?requester-nf-type=AMF&target-nf-type=AUSF&service-names=nausf-auth&limit=1"
        self.assertEqual(validate_candidate_path(path), path)
        for invalid in (
            "http://127.0.0.10:8000/nnrf-disc/v1/nf-instances?requester-nf-type=AMF&target-nf-type=AUSF&service-names=nausf-auth",
            "/nnrf-disc/v1/nf-instances?requester-nf-type=AMF&target-nf-type=AUSF&service-names=nausf-auth&limit=100",
            "/nnrf-disc/v1/nf-instances?requester-nf-type=AMF&requester-nf-type=UDM&target-nf-type=AUSF&service-names=nausf-auth",
            "/nnrf-disc/v1/nf-instances?requester-nf-type=AMF&target-nf-type=AUSF&service-names=nausf-auth&callback=http://example.invalid",
        ):
            with self.assertRaises(ValueError):
                validate_candidate_path(invalid)

    def test_input_hash_groups_are_assigned_to_only_one_split(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = Path(directory)
            cases = [
                InputCase("a1", "ordinary", "NRF discovery", "a" * 64, "corpus/ordinary/a1", "commit"),
                InputCase("a2", "llm_suggested", "NRF discovery", "a" * 64, "corpus/llm/a2", "commit", "model"),
                InputCase("b1", "llm_suggested", "NRF discovery", "b" * 64, "corpus/llm/b1", "commit", "model"),
            ]
            outcomes = [
                TestOutcome(f"o-{case.input_id}", case.input_id, f"R{index}",
                            "2026-10-01T12:00:00Z", "2026-10-01T12:00:01Z", "accepted")
                for index, case in enumerate(cases, start=1)
            ]
            labels = [RunLabel(outcome.run_id, "input_test", "train") for outcome in outcomes]
            write_jsonl(campaign / "input_cases.jsonl", cases)
            write_jsonl(campaign / "outcomes.jsonl", outcomes)
            write_jsonl(campaign / "run_labels.jsonl", labels)

            report = assign_input_test_splits(campaign, seed=7)
            assigned = {row.run_id: row.split for row in read_jsonl(campaign / "run_labels.jsonl", RunLabel)}

        self.assertEqual(assigned["R1"], assigned["R2"])
        self.assertNotEqual(assigned["R1"], assigned["R3"])
        self.assertEqual(report["distinct_input_hashes"], 2)


    def setUp(self):
        self.case = InputCase(
            input_id="case-001",
            input_source="llm_suggested",
            component="amf-nas-registration",
            input_sha256="a" * 64,
            corpus_path="corpus/llm/case-001.bin",
            free5gc_commit="4aa237be57404dea5b49ca8f332c6e25ede052de",
            generator_model="fixture-model-v1",
        )
        self.outcome = TestOutcome(
            outcome_id="outcome-001",
            input_id="case-001",
            run_id="RTEST001",
            window_start="2026-10-01T12:00:00Z",
            window_end="2026-10-01T12:00:01Z",
            status="crash",
            exit_code=1,
            signal="SIGABRT",
        )
        self.labels = [RunLabel("RTEST001", "input_test", "train")]

    def test_jsonl_round_trip_and_campaign_linkage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / "inputs.jsonl", [self.case])
            write_jsonl(root / "outcomes.jsonl", [self.outcome])
            write_jsonl(root / "run_labels.jsonl", self.labels)
            cases = read_jsonl(root / "inputs.jsonl", InputCase)
            outcomes = read_jsonl(root / "outcomes.jsonl", TestOutcome)
            labels = read_jsonl(root / "run_labels.jsonl", RunLabel)
            validate_campaign(cases, outcomes, labels)

        self.assertEqual(outcomes[0].status, "crash")
        self.assertEqual(outcomes[0].run_id, "RTEST001")

    def test_rejects_unsafe_paths_and_timezone_naive_windows(self):
        with self.assertRaises(ValueError):
            InputCase(**{**self.case.__dict__, "corpus_path": "../outside.bin"})
        with self.assertRaises(ValueError):
            TestOutcome(
                outcome_id="outcome-002",
                input_id="case-001",
                run_id="RTEST001",
                window_start="2026-10-01T12:00:00",
                window_end="2026-10-01T12:00:01Z",
                status="accepted",
            )

    def test_http_outcomes_preserve_status_and_latency(self):
        accepted = TestOutcome(
            outcome_id="http-200",
            input_id="case-001",
            run_id="RTEST001",
            window_start="2026-10-01T12:00:00Z",
            window_end="2026-10-01T12:00:01Z",
            status="accepted",
            http_status=200,
            duration_ms=23.26,
        )
        self.assertEqual(accepted.http_status, 200)
        self.assertEqual(accepted.duration_ms, 23.26)
        with self.assertRaisesRegex(ValueError, "2xx"):
            TestOutcome(
                outcome_id="bad-http-accepted",
                input_id="case-001",
                run_id="RTEST001",
                window_start="2026-10-01T12:00:00Z",
                window_end="2026-10-01T12:00:01Z",
                status="accepted",
                http_status=401,
            )

    def test_rejects_outcome_without_matching_input(self):
        unmatched = TestOutcome(
            outcome_id="outcome-002",
            input_id="missing-case",
            run_id="RTEST001",
            window_start="2026-10-01T12:00:00Z",
            window_end="2026-10-01T12:00:01Z",
            status="accepted",
        )
        with self.assertRaisesRegex(ValueError, "unknown input_id"):
            validate_campaign([self.case], [unmatched], self.labels)


class InputTestingEvaluationTests(unittest.TestCase):
    @patch("nwdaf_research.input_testing.nrf_discovery.subprocess.run")
    def test_llm_candidate_runner_records_generator_provenance(self, remote_run):
        class Observer:
            host = "127.0.0.1"
            port = 2222
            user = "lab-user"
            identity_file = None
            timeout = 5.0

            def __init__(self):
                self.times = iter(("2026-10-01T12:00:00+00:00", "2026-10-01T12:00:02+00:00"))

            def observe(self):
                return SimpleNamespace(
                    observed_at=next(self.times),
                    host="free5gc",
                    features={
                        "linux_load_1m_mean": 0.5,
                        "linux_memory_total_mean": 1000.0,
                        "linux_memory_available_mean": 500.0,
                    },
                    evidence={},
                    unavailable_features=[],
                )

        remote_run.return_value.returncode = 0
        remote_run.return_value.stdout = json.dumps({
            "window_start": "2026-10-01T12:00:00.500Z",
            "window_end": "2026-10-01T12:00:01Z",
            "http_status": 200,
            "duration_ms": 20.0,
            "free5gc_commit": "d" * 40,
            "before_snapshot": {
                "observed_at": "2026-10-01T12:00:00Z", "host": "free5gc",
                "features": {"linux_load_1m_mean": 0.5, "linux_memory_total_mean": 1000.0,
                              "linux_memory_available_mean": 500.0, "memory_available_ratio_mean": 0.5},
                "evidence": {"source": "remote_proc_snapshot"}, "unavailable_features": [],
            },
            "after_snapshot": {
                "observed_at": "2026-10-01T12:00:02Z", "host": "free5gc",
                "features": {"linux_load_1m_mean": 0.6, "linux_memory_total_mean": 1000.0,
                              "linux_memory_available_mean": 450.0, "memory_available_ratio_mean": 0.45},
                "evidence": {"source": "remote_proc_snapshot"}, "unavailable_features": [],
            },
            "linux_events": [], "sbi_events": [], "pfcp_events": [],
        })
        remote_run.return_value.stderr = ""
        candidate_path = (
            "/nnrf-disc/v1/nf-instances?service-names=nausf-auth&target-nf-type=AUSF"
            "&requester-nf-type=AMF&limit=1"
        )

        with tempfile.TemporaryDirectory() as directory:
            result = run_nrf_discovery_case(
                campaign_dir=directory,
                run_id="RLLM001",
                input_id="llm-nrf-002",
                nf_instance_id="b455d3f3-f92d-4f48-adc7-993e1beb1921",
                request_path=candidate_path,
                input_source="llm_suggested",
                generator_model="qwen2.5-coder:7b",
                observer=Observer(),
            )
            root = Path(directory)
            recorded_case = read_jsonl(root / "input_cases.jsonl", InputCase)[0]
            saved_request = (root / recorded_case.corpus_path).read_text(encoding="ascii").strip()

        self.assertEqual(recorded_case.input_source, "llm_suggested")
        self.assertEqual(recorded_case.generator_model, "qwen2.5-coder:7b")
        self.assertEqual(recorded_case.corpus_path, "corpus/llm/llm-nrf-002.txt")
        self.assertEqual(saved_request, candidate_path)
        self.assertEqual(result["http_status"], 200)

    @patch("nwdaf_research.input_testing.normal_baseline.subprocess.run")
    def test_passive_normal_baseline_creates_normal_run_without_request_record(self, remote_run):
        class Observer:
            host = "127.0.0.1"
            port = 2222
            user = "lab-user"
            identity_file = None
            timeout = 5.0

        remote_run.return_value.returncode = 0
        remote_run.return_value.stderr = ""
        remote_run.return_value.stdout = json.dumps({
            "started_at": "2026-10-01T12:00:00Z",
            "finished_at": "2026-10-01T12:00:02Z",
            "free5gc_commit": "f" * 40,
            "before_snapshot": {
                "observed_at": "2026-10-01T11:59:59Z", "host": "free5gc",
                "features": {"linux_load_1m_mean": 0.5, "linux_memory_total_mean": 1000.0,
                              "linux_memory_available_mean": 500.0, "memory_available_ratio_mean": 0.5},
                "evidence": {"source": "remote_proc_snapshot"}, "unavailable_features": [],
            },
            "after_snapshot": {
                "observed_at": "2026-10-01T12:00:03Z", "host": "free5gc",
                "features": {"linux_load_1m_mean": 0.6, "linux_memory_total_mean": 1000.0,
                              "linux_memory_available_mean": 450.0, "memory_available_ratio_mean": 0.45},
                "evidence": {"source": "remote_proc_snapshot"}, "unavailable_features": [],
            },
            "linux_events": [], "sbi_events": [], "pfcp_events": [],
        })

        with tempfile.TemporaryDirectory() as directory:
            result = capture_normal_baseline(
                campaign_dir=directory,
                split="held_out",
                duration_sec=2.0,
                observer=Observer(),
            )
            root = Path(directory)
            label = read_jsonl(root / "run_labels.jsonl", RunLabel)[0]
            self.assertFalse((root / "input_cases.jsonl").exists())
            self.assertFalse((root / "outcomes.jsonl").exists())

        self.assertEqual(result["label"], "normal")
        self.assertEqual(label.label, "normal")
        self.assertEqual(label.split, "held_out")

    def test_snapshot_materializer_writes_only_measured_linux_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = Path(directory)
            case = InputCase(
                "case-003", "ordinary", "NRF Nnrf_NFDiscovery", "e" * 64,
                "corpus/ordinary/case-003.txt", "f" * 40,
                auth_context="OAuth2 scope=nnrf-disc",
            )
            outcome = TestOutcome(
                "case-003-outcome", "case-003", "RLAB003",
                "2026-10-01T12:00:00.500Z", "2026-10-01T12:00:01.500Z",
                "accepted", http_status=200, duration_ms=23.0,
            )
            label = RunLabel("RLAB003", "input_test", "train")
            write_jsonl(campaign / "input_cases.jsonl", [case])
            write_jsonl(campaign / "outcomes.jsonl", [outcome])
            write_jsonl(campaign / "run_labels.jsonl", [label])
            snapshots = [
                {
                    "run_id": "RLAB003", "input_id": "case-003", "phase": "before",
                    "observed_at": "2026-10-01T12:00:00Z", "host": "free5gc",
                    "features": {
                        "linux_load_1m_mean": 0.5,
                        "linux_memory_total_mean": 1000,
                        "linux_memory_available_mean": 500,
                    },
                    "evidence": {"pfcp_recent_log_events": 8, "sbi_recent_log_events": 4},
                    "unavailable_features": [],
                },
                {
                    "run_id": "RLAB003", "input_id": "case-003", "phase": "after",
                    "observed_at": "2026-10-01T12:00:02Z", "host": "free5gc",
                    "features": {
                        "linux_load_1m_mean": 0.7,
                        "linux_memory_total_mean": 1000,
                        "linux_memory_available_mean": 400,
                    },
                    "evidence": {"pfcp_recent_log_events": 10, "sbi_recent_log_events": 5},
                    "unavailable_features": [],
                },
            ]
            (campaign / "live_observations.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in snapshots), encoding="utf-8"
            )

            run_dirs = materialize_input_test_runs(campaign)
            run_dir = run_dirs[0]
            features = RunFeatureBuilder(campaign / "runs").build_features_for_run("RLAB003")

            self.assertEqual(features["linux_event_count"], 2)
            self.assertEqual(features["linux_load_1m_mean"], 0.6)
            self.assertEqual(features["sbi_event_count"], 0)
            self.assertFalse((run_dir / "sbi" / "events.jsonl").exists())
            self.assertFalse((run_dir / "pfcp" / "events.jsonl").exists())
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertIn("summary only", metadata["telemetry_notes"]["pfcp"])

    @patch("nwdaf_research.input_testing.nrf_discovery.subprocess.run")
    def test_nrf_probe_records_real_http_metadata_without_token(self, remote_run):
        class Observer:
            host = "127.0.0.1"
            port = 2222
            user = "lab-user"
            identity_file = None
            timeout = 5.0
            timestamps = iter((
                "2026-10-01T12:00:00+00:00",
                "2026-10-01T12:00:02+00:00",
            ))

            def observe(self):
                return SimpleNamespace(
                    observed_at=next(self.timestamps),
                    host="free5gc",
                    features={
                        "linux_load_1m_mean": 0.5,
                        "linux_memory_total_mean": 1000.0,
                        "linux_memory_available_mean": 500.0,
                        "memory_available_ratio_mean": 0.5,
                    },
                    evidence={"pfcp_recent_log_events": 2},
                    unavailable_features=["sbi_event_rate"],
                )

        remote_run.return_value.returncode = 0
        remote_run.return_value.stdout = json.dumps({
            "window_start": "2026-10-01T12:00:01.000000000Z",
            "window_end": "2026-10-01T12:00:01.023000000Z",
            "http_status": 200,
            "duration_ms": 23.0,
            "free5gc_commit": "d" * 40,
            "before_snapshot": {
                "observed_at": "2026-10-01T12:00:00Z", "host": "free5gc",
                "features": {"linux_load_1m_mean": 0.5, "linux_memory_total_mean": 1000.0,
                              "linux_memory_available_mean": 500.0, "memory_available_ratio_mean": 0.5},
                "evidence": {"source": "remote_proc_snapshot"}, "unavailable_features": [],
            },
            "after_snapshot": {
                "observed_at": "2026-10-01T12:00:02Z", "host": "free5gc",
                "features": {"linux_load_1m_mean": 0.6, "linux_memory_total_mean": 1000.0,
                              "linux_memory_available_mean": 450.0, "memory_available_ratio_mean": 0.45},
                "evidence": {"source": "remote_proc_snapshot"}, "unavailable_features": [],
            },
            "linux_events": [{
                "run_id": "RLAB002", "source": "linux", "event_type": "host_sample",
                "event_time": "2026-10-01T12:00:00.250Z", "load_1m": 0.6,
                "memory_bytes": {"total": 1000, "available": 450},
            }],
            "sbi_events": [{
                "run_id": "RLAB002", "source": "sbi", "event_time": "2026-10-01T12:00:01Z",
                "nf_type": "NRF", "procedure": "/nnrf-disc/v1/nf-instances",
                "http_method": "GET", "status": 200, "latency_ms": None,
            }],
            "pfcp_events": [{
                "run_id": "RLAB002", "source": "pfcp", "event_time": "2026-10-01T12:00:01Z",
                "nf_type": "UPF", "message_type": "handleHeartbeatRequest",
                "direction": "request", "level": "info", "status": None, "latency_ms": None,
            }],
        })
        remote_run.return_value.stderr = ""

        with tempfile.TemporaryDirectory() as directory:
            result = run_nrf_discovery_case(
                campaign_dir=directory,
                run_id="RLAB002",
                input_id="case-nrf-002",
                nf_instance_id="b455d3f3-f92d-4f48-adc7-993e1beb1921",
                observer=Observer(),
            )
            root = Path(directory)
            case = read_jsonl(root / "input_cases.jsonl", InputCase)[0]
            outcome = read_jsonl(root / "outcomes.jsonl", TestOutcome)[0]
            labels = read_jsonl(root / "run_labels.jsonl", RunLabel)
            snapshots = [json.loads(line) for line in (root / "live_observations.jsonl").read_text().splitlines()]
            corpus = (root / case.corpus_path).read_bytes()
            self.assertEqual(result["event_counts"], {"linux": 1, "sbi": 1, "pfcp": 1})
            remote_command = remote_run.call_args.args[0][-1]
            remote_python = _remote_python_source()
            run_dir = root / "runs" / "RLAB002"
            run_features = RunFeatureBuilder(root / "runs").build_features_for_run("RLAB002")
            sbi_event = json.loads((run_dir / "sbi" / "events.jsonl").read_text().splitlines()[0])
            persisted = "\n".join(
                (root / filename).read_text(encoding="utf-8")
                for filename in ("input_cases.jsonl", "outcomes.jsonl", "run_labels.jsonl", "live_observations.jsonl")
            )

        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["outcome"], "accepted")
        self.assertEqual(outcome.duration_ms, 23.0)
        self.assertEqual(outcome.http_status, 200)
        self.assertEqual(case.input_sha256, hashlib.sha256(corpus).hexdigest())
        self.assertIn("scope=nnrf-disc", case.auth_context)
        self.assertEqual([row["phase"] for row in snapshots], ["before", "after"])
        self.assertEqual(labels[0].split, "train")
        self.assertEqual(run_features["linux_event_count"], 3)
        self.assertEqual(run_features["sbi_event_count"], 1)
        self.assertEqual(run_features["pfcp_event_count"], 1)
        self.assertEqual(run_features["sbi_telemetry_available"], 1.0)
        self.assertNotIn("client_ip", sbi_event)
        self.assertNotIn("raw_reference", sbi_event)
        self.assertIn("http://127.0.0.10:8000/nnrf-disc/v1/nf-instances?", remote_python)
        self.assertIn("registered = sys.argv[2]", remote_python)
        self.assertNotIn("mongosh", remote_python)
        self.assertNotIn('"access_token"', persisted)
        self.assertNotIn("fake-secret-token", persisted)
        self.assertNotIn("access_token", result)

    def test_remote_probe_shell_and_embedded_python_are_syntactically_valid(self):
        command = _remote_probe("RLAB004", "b455d3f3-f92d-4f48-adc7-993e1beb1921")
        remote_python = _remote_python_source()
        shell_check = subprocess.run(
            ["bash", "-n", "-c", command], text=True, capture_output=True
        )
        self.assertEqual(shell_check.returncode, 0, shell_check.stderr)
        compile(remote_python, "<remote_probe>", "exec")
        self.assertLess(remote_python.index("started_at = utc_now()"), remote_python.index("oauth2/token"))

    def test_normal_baseline_remote_script_is_passive_only(self):
        compile(REMOTE_BASELINE, "<remote_normal_baseline>", "exec")
        self.assertNotIn("urllib.request", REMOTE_BASELINE)
        self.assertNotIn("TrafficController", REMOTE_BASELINE)
        self.assertNotIn("scenario.start", REMOTE_BASELINE)
        self.assertNotIn("curl ", REMOTE_BASELINE)

    @patch("nwdaf_research.input_testing.nrf_discovery.subprocess.run")
    def test_nrf_probe_refuses_duplicate_ids_before_remote_call(self, remote_run):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / "run_labels.jsonl", [RunLabel("RLAB002", "input_test", "train")])
            with self.assertRaisesRegex(ValueError, "run_id already has a label"):
                run_nrf_discovery_case(
                    campaign_dir=root,
                    run_id="RLAB002",
                    input_id="case-nrf-002",
                    nf_instance_id="b455d3f3-f92d-4f48-adc7-993e1beb1921",
                    observer=object(),
                )
        remote_run.assert_not_called()

    def test_empty_campaign_scaffold_explains_what_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = Path(directory)
            for filename in ("input_cases.jsonl", "outcomes.jsonl", "run_labels.jsonl"):
                (campaign / filename).write_text("", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Campaign manifests are empty"):
                evaluate_campaign(campaign)

    def test_unbalanced_campaign_reports_required_run_classes_and_splits(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = Path(directory)
            case = InputCase(
                "case-001", "ordinary", "NRF Nnrf_NFDiscovery", "a" * 64,
                "corpus/ordinary/case-001.txt", "free5gc-test-commit",
                auth_context="OAuth2 scope=nnrf-disc",
            )
            outcome = TestOutcome(
                "outcome-001", "case-001", "RLAB003",
                "2026-10-01T12:00:00Z", "2026-10-01T12:00:01Z", "accepted",
                http_status=200,
            )
            write_jsonl(campaign / "input_cases.jsonl", [case])
            write_jsonl(campaign / "outcomes.jsonl", [outcome])
            write_jsonl(campaign / "run_labels.jsonl", [RunLabel("RLAB003", "input_test", "train")])

            with self.assertRaisesRegex(ValueError, "normal and input_test runs"):
                evaluate_campaign(campaign)

    def test_evaluate_campaign_joins_records_to_campaign_local_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = root / "campaign"
            runs_root = campaign / "runs"
            campaign.mkdir()
            cases = [
                InputCase("ordinary-01", "ordinary", "amf-nas-registration", "b" * 64,
                          "corpus/ordinary/01.bin", "free5gc-test-commit"),
                InputCase("llm-01", "llm_suggested", "amf-nas-registration", "c" * 64,
                          "corpus/llm/01.bin", "free5gc-test-commit", "fixture-model-v1"),
            ]
            labels = []
            outcomes = []
            runs_root.mkdir()
            run_specs = [
                ("N1", "normal", "train", 0.0),
                ("N2", "normal", "train", 0.1),
                ("T1", "input_test", "train", 1.0),
                ("T2", "input_test", "train", 0.9),
                ("N3", "normal", "held_out", 0.05),
                ("N4", "normal", "held_out", 0.15),
                ("T3", "input_test", "held_out", 0.95),
                ("T4", "input_test", "held_out", 0.85),
            ]
            for index, (run_id, label, split, load) in enumerate(run_specs):
                labels.append(RunLabel(run_id, label, split))
                run_dir = runs_root / run_id
                (run_dir / "linux").mkdir(parents=True)
                (run_dir / "metadata.json").write_text(
                    json.dumps({"run_id": run_id, "duration_sec": 1}), encoding="utf-8"
                )
                (run_dir / "ground_truth.json").write_text(
                    json.dumps({"class": label, "anomalous": label == "input_test"}), encoding="utf-8"
                )
                (run_dir / "timeline.json").write_text(
                    json.dumps({"timeline": {"T0": "2026-10-01T12:00:00Z"}}), encoding="utf-8"
                )
                (run_dir / "linux" / "events.jsonl").write_text(
                    json.dumps({"event_type": "host_sample", "load_1m": load,
                                "memory_bytes": {"total": 1000, "available": 500}}) + "\n",
                    encoding="utf-8",
                )
                if label == "input_test":
                    outcomes.append(TestOutcome(
                        f"outcome-{index}", "ordinary-01" if index % 2 else "llm-01", run_id,
                        "2026-10-01T12:00:00Z", "2026-10-01T12:00:01Z", "rejected",
                    ))

            write_jsonl(campaign / "input_cases.jsonl", cases)
            write_jsonl(campaign / "outcomes.jsonl", outcomes)
            write_jsonl(campaign / "run_labels.jsonl", labels)
            report_path = campaign / "evaluation.json"

            report = evaluate_campaign(campaign, output_path=report_path)

            saved = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["run_label_counts"]["held_out"]["normal"], 2)
            self.assertEqual(report["run_detection_evaluation"]["metrics"]["run_count"], 4)
            self.assertEqual(
                set(report["feature_sensitivity"]),
                {"all_features", "without_duration", "linux_only", "interpretation"},
            )
            self.assertIn("collection-procedure signatures", report["feature_sensitivity"]["interpretation"])
            self.assertEqual(saved["campaign_id"], "campaign")
            self.assertNotIn("ground_truth_class", saved["run_detection_evaluation"]["feature_names"])

    def test_live_snapshots_append_with_run_and_input_links(self):
        class Observer:
            def observe(self):
                return SimpleNamespace(
                    observed_at="2026-10-01T12:00:00+00:00",
                    host="free5gc",
                    features={"linux_load_1m_mean": 0.5},
                    evidence={"pfcp_recent_log_events": 2},
                    unavailable_features=["sbi_event_rate"],
                )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "observations.jsonl"
            before = capture_live_observation(
                observer=Observer(), run_id="RTEST01", input_id="case-01",
                phase="before", output_path=output,
            )
            after = capture_live_observation(
                observer=Observer(), run_id="RTEST01", input_id="case-01",
                phase="after", output_path=output,
            )
            saved = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

        self.assertEqual([record["phase"] for record in saved], ["before", "after"])
        self.assertTrue(all(record["run_id"] == "RTEST01" for record in saved))
        self.assertTrue(all(record["input_id"] == "case-01" for record in saved))
        self.assertEqual(before["host"], after["host"])

    def test_live_snapshot_rejects_unknown_phase(self):
        with self.assertRaisesRegex(ValueError, "phase"):
            capture_live_observation(
                observer=object(), run_id="RTEST01", input_id="case-01",
                phase="during", output_path="unused.jsonl",
            )

    def test_compares_ordinary_and_llm_outcomes_without_vulnerability_claims(self):
        ordinary = InputCase(
            input_id="ordinary-001",
            input_source="ordinary",
            component="amf-nas-registration",
            input_sha256="b" * 64,
            corpus_path="corpus/ordinary/case-001.bin",
            free5gc_commit="4aa237be57404dea5b49ca8f332c6e25ede052de",
        )
        llm = InputCase(
            input_id="llm-001",
            input_source="llm_suggested",
            component="amf-nas-registration",
            input_sha256="b" * 64,
            corpus_path="corpus/llm/case-001.bin",
            free5gc_commit="4aa237be57404dea5b49ca8f332c6e25ede052de",
            generator_model="fixture-model-v1",
            trial_group="fixture-group",
            replicate_index=1,
            template_choice=2,
        )
        outcomes = [
            TestOutcome("o1", "ordinary-001", "R1", "2026-10-01T12:00:00Z", "2026-10-01T12:00:01Z", "accepted", http_status=200, duration_ms=20.0),
            TestOutcome("o2", "llm-001", "R2", "2026-10-01T12:00:00Z", "2026-10-01T12:00:01Z", "accepted", http_status=200, duration_ms=25.0),
        ]

        summary = compare_input_outcomes([ordinary, llm], outcomes)

        self.assertEqual(summary["ordinary"]["status_counts"]["accepted"], 1)
        self.assertEqual(summary["llm_suggested"]["crash_observation_rate"], 0.0)
        self.assertEqual(summary["llm_suggested"]["inputs_with_outcomes"], 1)
        self.assertEqual(len(summary["matched_by_sha256"]), 1)
        self.assertEqual(summary["matched_by_sha256"][0]["llm_minus_ordinary_duration_ms"], 5.0)
        self.assertEqual(summary["llm_by_model"]["fixture-model-v1"]["input_count"], 1)
        self.assertEqual(summary["llm_by_trial_group"]["fixture-group"]["replicate_indices"], [1])

    def test_feature_projection_excludes_identifiers_and_labels(self):
        class Builder:
            def build_features_for_run(self, run_id):
                return {
                    "run_id": run_id,
                    "ground_truth_class": "input_test",
                    "scenario_id": "should-not-enter-model",
                    "linux_load_1m_mean": 0.75,
                    "sbi_event_count": 3,
                }

        projected = features_for_runs(Builder(), ["R1"])
        self.assertEqual(projected["R1"]["linux_load_1m_mean"], 0.75)
        self.assertEqual(projected["R1"]["sbi_event_count"], 3.0)
        self.assertNotIn("ground_truth_class", projected["R1"])
        self.assertNotIn("scenario_id", projected["R1"])

    def test_evaluation_trains_on_train_and_scores_held_out_runs(self):
        rows = [
            ("N1", "normal", "train", 0.0),
            ("N2", "normal", "train", 0.1),
            ("T1", "input_test", "train", 1.0),
            ("T2", "input_test", "train", 0.9),
            ("N3", "normal", "held_out", 0.05),
            ("N4", "normal", "held_out", 0.15),
            ("T3", "input_test", "held_out", 0.95),
            ("T4", "input_test", "held_out", 0.85),
        ]
        features = {run_id: {"linux_load_1m_mean": load} for run_id, _, _, load in rows}
        labels = [RunLabel(run_id, label, split) for run_id, label, split, _ in rows]

        result = evaluate_run_detection(features, labels)

        self.assertEqual(set(result["train_run_ids"]), {"N1", "N2", "T1", "T2"})
        self.assertEqual(set(result["held_out_run_ids"]), {"N3", "N4", "T3", "T4"})
        self.assertEqual(result["metrics"]["run_count"], 4)
        self.assertEqual(result["metrics"]["confusion_matrix"]["tn"], 2)
        self.assertEqual(result["metrics"]["confusion_matrix"]["tp"], 2)
        self.assertNotIn("vulnerability", result)


if __name__ == "__main__":
    unittest.main()