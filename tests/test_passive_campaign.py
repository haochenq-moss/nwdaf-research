import ast
import io
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from nwdaf_research.live.passive_campaign import (
    BASELINE_CONTRACT, CLOCK_BASIS, COUNTERS, EVENT_FIELDS, MAX_CAPTURE_BYTES, REMOTE_CODE, SOURCE_ID,
    CaptureError, _publish_exclusive, acquire_capture, process_capture, run_campaign,
)
from nwdaf_research.live.ssh_observer import SSHLiveObserver

REPOSITORY = Path(__file__).resolve().parents[1]


def valid_capture(window_count=3, duration_sec=10):
    anchor = datetime(2026, 10, 3, tzinfo=timezone.utc)
    anchor_ns = 1_000_000_000
    capture = {"schema": "passive-campaign-v1", "contract": BASELINE_CONTRACT, "clock_basis": CLOCK_BASIS,
        "anchor_monotonic_ns": anchor_ns, "anchor_projected_utc": anchor.isoformat(),
        "hostname": "fixture-host", "boot_id": "11111111-1111-4111-8111-111111111111",
        "collector_instance_id": "22222222-2222-4222-8222-222222222222", "git_revision": "a" * 40,
        "parser_paths": {source: "research/collectors/" + source + ".py" for source in ("sbi", "pfcp")},
        "parser_sha256": {"sbi": "b" * 64, "pfcp": "c" * 64},
        "warmup_sec": 30, "window_count": window_count, "duration_sec": duration_sec,
        "read_budget": {"source_poll_bytes": 2097152, "per_log_bytes": 524288, "aggregate_poll_bytes": 2097152},
        "capture_errors": [], "snapshots": []}
    capture["clock_domain"] = capture["hostname"] + "/" + capture["boot_id"] + "/CLOCK_MONOTONIC"
    for index in range(31 + window_count * duration_sec):
        timestamp = (anchor + timedelta(seconds=index)).isoformat()
        timestamp_ns = anchor_ns + index * 1_000_000_000
        counters = dict.fromkeys(COUNTERS, 0)
        counters["linux_event_count"] = index + 1
        collectors = {}
        heartbeats = {}
        for source in ("linux", "sbi", "pfcp"):
            collectors[source] = {"heartbeat_at": timestamp, "collector_healthy": True,
                                  "telemetry_source_synced": True, "observed_through": timestamp}
            heartbeats[source] = {"source_id": SOURCE_ID, "collector_instance_id": capture["collector_instance_id"],
                "hostname": capture["hostname"], "boot_id": capture["boot_id"], "clock_domain": capture["clock_domain"],
                "clock": "CLOCK_MONOTONIC", "timestamp_ns": timestamp_ns, "window_watermark_ns": timestamp_ns,
                "sequence_no": index, "status": "HEALTHY", "metrics_summary": {"events_observed": counters[source + "_event_count"], "drops": 0}}
        capture["snapshots"].append({"type": "snapshot", "index": index, "observed_at": timestamp,
            "monotonic_ns": timestamp_ns, "counters": counters, "collectors": collectors, "heartbeats": heartbeats,
            "linux_sample": {"load_1m": 0.1, "memory_total": 100, "memory_available": 40},
            "events": {"sbi": [], "pfcp": []}, "poll_errors": {source: [] for source in collectors}})
    return capture


def fault(capture, index, source, code="log_read_failed"):
    row = capture["snapshots"][index]
    row["poll_errors"][source] = [code]
    row["collectors"][source]["collector_healthy"] = False
    row["collectors"][source]["telemetry_source_synced"] = False
    row["heartbeats"][source]["status"] = "FAILED"
    row["heartbeats"][source]["metrics_summary"]["drops"] = None
    capture["capture_errors"].append(source + ":" + code)


class PassiveCampaignTests(unittest.TestCase):
    def test_zero_telemetry_is_ready_only_with_successful_known_sources(self):
        capture = valid_capture()
        self.assertEqual(len(capture["snapshots"]), 61)
        result = process_capture(capture)
        self.assertEqual(result["report"]["status"], "READY")
        self.assertEqual(result["report"]["window_status_counts"], {"READY": 3})
        for index, window in enumerate(result["windows"]):
            self.assertEqual(window["metadata"]["start_index"], 30 + 10 * index)
            self.assertEqual(window["metadata"]["end_index"], 40 + 10 * index)
            self.assertEqual(window["stream"][-1]["type"], "seal")
            features = window["readiness"]["features"]
            self.assertEqual(len(features), 16)
            self.assertEqual(features["linux_event_count"], 10)
            self.assertEqual(features["sbi_event_count"], 0)
            self.assertEqual(features["pfcp_event_count"], 0)
            self.assertEqual(features["sbi_telemetry_available"], 1.0)
            self.assertEqual(features["pfcp_telemetry_available"], 1.0)
            self.assertEqual([item["status"] for item in window["readiness"]["lifecycle"]], ["ACCUMULATING", "READY"])
        self.assertEqual(result["windows"][0]["stream"][-2], result["windows"][1]["stream"][0])

    def test_early_warmup_fault_cannot_be_reset_by_healthy_polls(self):
        capture = valid_capture()
        fault(capture, 3, "sbi")
        result = process_capture(capture)
        self.assertEqual(result["report"]["status"], "COLLECTOR_UNAVAILABLE")
        self.assertEqual(result["report"]["warmup"]["status"], "COLLECTOR_UNAVAILABLE")
        self.assertTrue(all(not window["readiness"]["features"] for window in result["windows"]))

    def test_absent_log_baseline_does_not_certify_zero(self):
        capture = valid_capture()
        for index in range(61):
            for source in ("sbi", "pfcp"):
                fault(capture, index, source, "log_baseline_failed")
        capture["capture_errors"] = sorted(set(capture["capture_errors"]))
        result = process_capture(capture)
        self.assertEqual(result["report"]["window_status_counts"], {"COLLECTOR_UNAVAILABLE": 3})

    def test_window_fault_is_sticky_and_independent_of_other_sources(self):
        capture = valid_capture()
        fault(capture, 35, "pfcp", "parser_failed")
        result = process_capture(capture)
        self.assertEqual(result["report"]["warmup"]["status"], "READY")
        self.assertEqual(result["windows"][0]["readiness"]["status"], "COLLECTOR_UNAVAILABLE")
        self.assertEqual(result["windows"][0]["readiness"]["features"], {})
        self.assertEqual(result["windows"][1]["readiness"]["status"], "READY")

    def test_transient_counter_zero_preserves_regression_evidence(self):
        capture = valid_capture()
        for row in capture["snapshots"]:
            value = 0 if row["index"] == 35 else 7
            row["counters"]["pfcp_request_count"] = value
            row["counters"]["pfcp_event_count"] = value
            row["heartbeats"]["pfcp"]["metrics_summary"]["events_observed"] = value
        result = process_capture(capture)
        readiness = result["windows"][0]["readiness"]
        self.assertEqual(readiness["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("counter regression/reset: pfcp_event_count", readiness["evidence_errors"])
        self.assertEqual(readiness["features"], {})

    def test_warmup_subcounter_regression_blocks_admission(self):
        capture = valid_capture()
        for row in capture["snapshots"]:
            row["counters"]["sbi_error_event_count"] = 0 if row["index"] == 5 else 1
            row["counters"]["sbi_event_count"] = 1
            row["heartbeats"]["sbi"]["metrics_summary"]["events_observed"] = 1
        self.assertFalse(process_capture(capture)["windows"][0]["metadata"]["warmup_admitted"])

    def test_nonmonotonic_and_future_watermarks_rejected(self):
        for field in ("monotonic_ns", "watermark"):
            capture = valid_capture()
            if field == "monotonic_ns":
                capture["snapshots"][4][field] = capture["snapshots"][3][field]
            else:
                capture["snapshots"][4]["heartbeats"]["pfcp"]["window_watermark_ns"] += 1
            with self.subTest(field=field), self.assertRaises(CaptureError):
                process_capture(capture)

    def test_flags_are_not_coerced(self):
        for value in (1, "true", None):
            capture = valid_capture()
            capture["snapshots"][4]["collectors"]["sbi"]["collector_healthy"] = value
            with self.subTest(value=value), self.assertRaises(CaptureError):
                process_capture(capture)

    def test_projection_uses_actual_jittered_endpoints(self):
        capture = valid_capture()
        anchor = datetime.fromisoformat(capture["anchor_projected_utc"])
        for row in capture["snapshots"]:
            jitter_ns = (row["index"] % 3) * 20_000_000
            row["monotonic_ns"] += jitter_ns
            timestamp = (anchor + timedelta(microseconds=(row["monotonic_ns"] - capture["anchor_monotonic_ns"]) // 1000)).isoformat()
            row["observed_at"] = timestamp
            for source in row["collectors"]:
                row["collectors"][source]["heartbeat_at"] = timestamp
                row["collectors"][source]["observed_through"] = timestamp
                row["heartbeats"][source]["timestamp_ns"] = row["monotonic_ns"]
                row["heartbeats"][source]["window_watermark_ns"] = row["monotonic_ns"]
        result = process_capture(capture)
        self.assertEqual(result["report"]["status"], "READY")
        self.assertEqual(result["windows"][0]["readiness"]["features"]["duration_sec"], 10.02)

    def test_one_strict_read_only_acquisition_and_bounded_timeout(self):
        execute = Mock(return_value=SimpleNamespace(stdout=json.dumps(valid_capture())))
        observer = SSHLiveObserver()
        with patch.object(observer, "observe", side_effect=AssertionError("legacy acquisition forbidden")):
            acquire_capture(observer, window_count=3, duration_sec=10, execute=execute)
        execute.assert_called_once()
        command = execute.call_args.args[0]
        self.assertEqual(command[:3], ["ssh", "-p", "2222"])
        self.assertIn("haochenqin-moss@127.0.0.1", command)
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertNotIn("StrictHostKeyChecking=accept-new", command)
        self.assertIn(str(Path.home() / ".ssh/id_ecdsa"), command)
        self.assertEqual(execute.call_args.kwargs["timeout"], 100)
        self.assertNotIn("sudo", command[-1])
        self.assertNotIn("REMOTE_SNAPSHOT", command[-1])

    def test_transport_errors_never_expose_stderr_or_payload(self):
        execute = Mock(side_effect=subprocess.CalledProcessError(1, "secret command", stderr="subscriber secret"))
        with self.assertRaises(CaptureError) as caught:
            acquire_capture(SSHLiveObserver(), window_count=3, duration_sec=10, execute=execute)
        self.assertEqual(str(caught.exception), "capture failed: CalledProcessError")

    def test_capture_size_and_remote_error_messages_are_bounded(self):
        cases = (
            ("x" * (MAX_CAPTURE_BYTES + 1), "capture output exceeds bound"),
            (json.dumps({"acquisition_error_type": "CaptureDeadline"}), "remote acquisition failed: CaptureDeadline"),
            (json.dumps({"acquisition_error_type": "subscriber-key-secret"}), "remote acquisition failed: RemoteError"),
        )
        for payload, expected in cases:
            execute = Mock(return_value=SimpleNamespace(stdout=payload))
            with self.subTest(expected=expected), self.assertRaises(CaptureError) as caught:
                acquire_capture(SSHLiveObserver(), window_count=3, duration_sec=10, execute=execute)
            self.assertEqual(str(caught.exception), expected)

    def test_short_or_gapped_warmup_cannot_be_ready(self):
        for increment_ns in (900_000_000, 2_100_000_000):
            capture = valid_capture(1, 2)
            anchor = datetime.fromisoformat(capture["anchor_projected_utc"])
            for row in capture["snapshots"]:
                row["monotonic_ns"] = capture["anchor_monotonic_ns"] + row["index"] * increment_ns
                timestamp = (anchor + timedelta(microseconds=(row["monotonic_ns"] - capture["anchor_monotonic_ns"]) // 1000)).isoformat()
                row["observed_at"] = timestamp
                for source in row["collectors"]:
                    row["collectors"][source]["heartbeat_at"] = timestamp
                    row["collectors"][source]["observed_through"] = timestamp
                    row["heartbeats"][source]["timestamp_ns"] = row["monotonic_ns"]
                    row["heartbeats"][source]["window_watermark_ns"] = row["monotonic_ns"]
            with self.subTest(increment_ns=increment_ns):
                result = process_capture(capture, window_count=1, duration_sec=2)
                self.assertEqual(result["report"]["status"], "COLLECTOR_UNAVAILABLE")
                self.assertEqual(result["windows"][0]["readiness"]["features"], {})

    def test_unexpected_event_fields_and_sensitive_values_rejected(self):
        for event in ({"raw": "subscriber secret"}, {"procedure": "imsi-12345"}):
            capture = valid_capture()
            timestamp = capture["snapshots"][31]["observed_at"]
            capture["snapshots"][31]["events"]["sbi"] = [{"event_time": timestamp, "collection_time": timestamp, **event}]
            with self.subTest(event=event), self.assertRaises(CaptureError):
                process_capture(capture)

    def test_existing_campaign_rejected_before_ssh(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            execute = Mock()
            with self.assertRaises(FileExistsError):
                run_campaign(parent, execute=execute)
            execute.assert_not_called()

    def test_symlink_parent_rejected_before_ssh(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            symlink = Path(parent) / "link"
            symlink.symlink_to(parent, target_is_directory=True)
            execute = Mock()
            with self.assertRaises(OSError):
                run_campaign(symlink / "campaign", execute=execute)
            execute.assert_not_called()

    def test_invalid_capture_leaves_no_campaign(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            destination = Path(parent) / "campaign"
            execute = Mock(return_value=SimpleNamespace(stdout='{"raw":"secret"}'))
            with self.assertRaises(CaptureError):
                run_campaign(destination, execute=execute)
            self.assertEqual(list(Path(parent).iterdir()), [])

    def test_destination_created_during_acquisition_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            destination = Path(parent) / "campaign"
            def execute(*args, **kwargs):
                destination.mkdir()
                (destination / "user-data").write_text("keep")
                return SimpleNamespace(stdout=json.dumps(valid_capture()))
            with self.assertRaises(FileExistsError):
                run_campaign(destination, execute=execute)
            self.assertEqual((destination / "user-data").read_text(), "keep")
            self.assertEqual(list(Path(parent).iterdir()), [destination])

    def test_exclusive_publication_failure_rolls_back_its_files(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            destination = Path(parent) / "campaign"
            execute = Mock(return_value=SimpleNamespace(stdout=json.dumps(valid_capture())))
            original_link = os.link
            calls = []
            def failing_link(*args, **kwargs):
                calls.append(args)
                if len(calls) == 2:
                    raise OSError("publication failure")
                return original_link(*args, **kwargs)
            with patch("nwdaf_research.live.passive_campaign._publish", side_effect=_publish_exclusive), patch("os.link", side_effect=failing_link):
                with self.assertRaises(OSError):
                    run_campaign(destination, execute=execute)
            self.assertEqual(list(Path(parent).iterdir()), [])

    def test_exclusive_publication_does_not_overwrite_concurrent_entry(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            destination = Path(parent) / "campaign"
            execute = Mock(return_value=SimpleNamespace(stdout=json.dumps(valid_capture())))
            original_link = os.link
            def conflicting_link(source, target, **kwargs):
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode=0o600, dir_fd=kwargs["dst_dir_fd"])
                with os.fdopen(descriptor, "w") as stream:
                    stream.write("keep")
                return original_link(source, target, **kwargs)
            with patch("nwdaf_research.live.passive_campaign._publish", side_effect=_publish_exclusive), patch("os.link", side_effect=conflicting_link):
                with self.assertRaises(FileExistsError):
                    run_campaign(destination, execute=execute)
            self.assertEqual((destination / "capture.json").read_text(), "keep")
            self.assertEqual(list(Path(parent).iterdir()), [destination])

    def test_persistence_layout_and_no_inference_or_network_actions(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            destination = Path(parent) / "campaign"
            execute = Mock(return_value=SimpleNamespace(stdout=json.dumps(valid_capture())))
            with patch("subprocess.run", side_effect=AssertionError("real subprocess forbidden")):
                summary = run_campaign(destination, execute=execute)
            self.assertEqual(summary["status"], "READY")
            self.assertEqual({path.name for path in destination.iterdir()}, {"manifest.json", "capture.json", "windows", "report.json"})
            report = json.loads((destination / "report.json").read_text())
            self.assertFalse(report["inference_performed"])
            self.assertFalse(report["network_transmission_executed"])
            self.assertTrue(report["active_ue_not_modified"])
            for folder in sorted((destination / "windows").iterdir()):
                self.assertEqual({path.name for path in folder.iterdir()}, {"metadata.json", "readiness.json", "snapshots.jsonl"})
                records = [json.loads(line) for line in (folder / "snapshots.jsonl").read_text().splitlines()]
                self.assertEqual(len(records), 12)
                self.assertEqual(records[-1]["type"], "seal")

    def test_duration_and_count_bounds(self):
        for count, duration in ((0, 10), (4, 10), (True, 10), (3, 1), (3, 11), (3, 2.0)):
            execute = Mock()
            with self.subTest(count=count, duration=duration), self.assertRaises(ValueError):
                acquire_capture(SSHLiveObserver(), window_count=count, duration_sec=duration, execute=execute)
            execute.assert_not_called()
        self.assertEqual(process_capture(valid_capture(1, 2), window_count=1, duration_sec=2)["report"]["status"], "READY")


class RemotePollerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace = {"__name__": "passive_fixture"}
        exec(compile(REMOTE_CODE, "<passive-fixture>", "exec"), cls.namespace)

    def poller(self, folder, sbi=None, pfcp=None):
        return self.namespace["CursorPoller"](str(folder), {"sbi": sbi or (lambda line: None), "pfcp": pfcp or (lambda line: None)}, 0)

    def test_parser_hash_tracks_content_and_refuses_symlinks_or_oversize(self):
        import hashlib

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "parser.py"
            path.write_bytes(b"first parser")
            self.assertEqual(self.namespace["parser_digest"](str(path)), hashlib.sha256(b"first parser").hexdigest())
            path.write_bytes(b"changed parser")
            self.assertNotEqual(self.namespace["parser_digest"](str(path)), hashlib.sha256(b"first parser").hexdigest())
            link = Path(directory) / "link.py"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                self.namespace["parser_digest"](str(link))
            path.write_bytes(b"x" * 262145)
            with self.assertRaisesRegex(ValueError, "parser_size_limit"):
                self.namespace["parser_digest"](str(path))

    def test_newest_log_run_excludes_archived_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = root / "20261002_100000"
            new = root / "20261003_100000"
            old.mkdir()
            new.mkdir()
            (old / "free5gc.log").write_text("old\n")
            (new / "free5gc.log").write_text("current\n")
            for index in range(140):
                (old / f"archive-{index}.log").touch()
            selected = self.namespace["select_log_root"](str(root))
            self.assertEqual(selected, str(new))
            self.assertEqual(self.poller(Path(selected)).initial_errors, [])

    def test_payload_is_python38_and_has_no_thread_start_or_hidden_reader(self):
        tree = ast.parse(REMOTE_CODE, feature_version=(3, 8))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        attributes = {node.func.attr for node in calls if isinstance(node.func, ast.Attribute)}
        self.assertNotIn("start", attributes)
        self.assertNotIn("_read_new", attributes)
        self.assertNotIn("sleep", attributes)
        self.assertIn("wait", attributes)
        self.assertNotIn("sudo", REMOTE_CODE)

    def test_eof_baseline_partial_lines_counts_and_sanitization(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as folder:
            path = Path(folder) / "nf.log"
            path.write_text("old SBI\nold PFCP\n")
            def sbi(line):
                return {"status": 500, "nf_type": "AMF", "raw": "secret", "procedure": "/subscribers/secret"} if line == "SBI" else None
            def pfcp(line):
                return {"direction": "request", "message_type": "Session Establishment Request", "address": "secret"} if line == "PFCP" else None
            poller = self.poller(folder, sbi, pfcp)
            linux, events, errors = poller.poll()
            self.assertTrue(linux)
            self.assertFalse(any(errors.values()))
            self.assertEqual(poller.counts["sbi_event_count"], 0)
            with path.open("a") as stream:
                stream.write("SB")
            self.assertEqual(poller.poll()[1]["sbi"], [])
            with path.open("a") as stream:
                stream.write("I\nPFCP\n")
            _, events, errors = poller.poll()
            self.assertFalse(any(errors.values()))
            self.assertEqual(poller.counts["sbi_event_count"], 1)
            self.assertEqual(poller.counts["sbi_error_event_count"], 1)
            self.assertEqual(poller.counts["pfcp_request_count"], 1)
            self.assertEqual(poller.counts["linux_event_count"], 3)
            for source in events:
                self.assertTrue(set(events[source][0]).issubset(EVENT_FIELDS[source]))
                self.assertNotIn("secret", json.dumps(events[source]))

    def test_missing_logs_never_healthy(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as folder:
            poller = self.poller(folder)
            errors = poller.poll()[2]
            self.assertIn("log_baseline_failed", errors["sbi"])
            self.assertIn("log_baseline_failed", errors["pfcp"])

    def test_parser_exception_denies_only_its_source(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as folder:
            path = Path(folder) / "nf.log"
            path.touch()
            poller = self.poller(folder, sbi=Mock(side_effect=RuntimeError("secret")))
            path.write_text("new line\n")
            errors = poller.poll()[2]
            self.assertEqual(errors["sbi"], ["parser_failed"])
            self.assertEqual(errors["pfcp"], [])

    def test_rotation_truncation_and_failed_reads_deny_sources(self):
        for mode in ("replacement", "truncation", "missing", "read_failure"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(dir=REPOSITORY) as folder:
                path = Path(folder) / "nf.log"
                path.write_text("history\n")
                poller = self.poller(folder)
                if mode == "replacement":
                    path.rename(Path(folder) / "old.txt")
                    path.touch()
                elif mode == "truncation":
                    path.write_text("")
                elif mode == "missing":
                    path.unlink()
                if mode == "read_failure":
                    with patch.dict(self.namespace, {"open_log": Mock(side_effect=OSError("secret"))}):
                        errors = poller.poll()[2]
                else:
                    errors = poller.poll()[2]
                self.assertTrue(errors["sbi"])
                self.assertTrue(errors["pfcp"])

    def test_exhausted_read_cap_denies_health(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as folder:
            path = Path(folder) / "nf.log"
            path.touch()
            poller = self.poller(folder)
            path.write_bytes(b"x" * (512 * 1024 + 1))
            errors = poller.poll()[2]
            self.assertIn("log_read_cap_exhausted", errors["sbi"])
            self.assertIn("log_read_cap_exhausted", errors["pfcp"])

    def test_new_log_history_risk_and_fresh_log_from_zero(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as folder:
            (Path(folder) / "known.log").touch()
            poller = self.poller(folder, sbi=lambda line: {"status": 200})
            fresh = Path(folder) / "new.log"
            fresh.write_text("new\n")
            with patch.dict(self.namespace, {"birth_time_ns": lambda descriptor: 2}):
                self.assertEqual(poller.poll()[1]["sbi"][0]["status"], 200)
            old = Path(folder) / "old.log"
            old.write_text("history\n")
            os.utime(old, ns=(0, 0))
            poller.started_wall_ns = 1
            errors = poller.poll()[2]
            self.assertIn("new_log_history_risk", errors["sbi"])

    def test_unknown_birth_time_and_old_birth_time_are_not_ctime(self):
        for birth in (None, 0):
            with self.subTest(birth=birth), tempfile.TemporaryDirectory(dir=REPOSITORY) as folder:
                (Path(folder) / "known.log").touch()
                poller = self.poller(folder, sbi=lambda line: {"status": 200})
                poller.started_wall_ns = 1
                (Path(folder) / "moved.log").write_text("old history\n")
                with patch.dict(self.namespace, {"birth_time_ns": lambda descriptor: birth}):
                    _, events, errors = poller.poll()
                self.assertEqual(events["sbi"], [])
                self.assertIn("new_log_history_risk", errors["sbi"])

    def test_pathname_replacement_during_read_is_not_healthy(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as folder:
            path = Path(folder) / "nf.log"
            path.touch()
            poller = self.poller(folder)
            original_read = os.read
            def replacing_read(descriptor, budget):
                data = original_read(descriptor, budget)
                path.rename(Path(folder) / "removed.txt")
                path.touch()
                return data
            with patch.object(self.namespace["os"], "read", side_effect=replacing_read):
                errors = poller.poll()[2]
            self.assertIn("log_changed_during_read", errors["sbi"])
            self.assertIn("log_changed_during_read", errors["pfcp"])

    def test_remote_deadline_cannot_be_swallowed_by_poll_errors(self):
        deadline = self.namespace["CaptureDeadline"]
        self.assertFalse(issubclass(deadline, Exception))
        callbacks = []
        fake_signal = SimpleNamespace(SIGALRM=14, ITIMER_REAL=0,
            signal=Mock(side_effect=lambda code, handler: callbacks.append(handler) or None), setitimer=Mock())
        def blocked_capture(count, duration):
            callbacks[0](14, None)
        with patch.dict(self.namespace, {"signal": fake_signal, "capture": blocked_capture}):
            with self.assertRaises(deadline):
                self.namespace["bounded_capture"](3, 10)
        self.assertEqual(fake_signal.setitimer.call_args_list[0].args, (0, 88.0))
        self.assertEqual(fake_signal.setitimer.call_args_list[-1].args, (0, 0))

    def test_preexisting_partial_line_is_not_admitted(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as folder:
            path = Path(folder) / "nf.log"
            path.write_text("preexisting")
            poller = self.poller(folder, sbi=lambda line: {"status": 200})
            with path.open("a") as stream:
                stream.write(" continuation")
            self.assertEqual(poller.poll()[1]["sbi"], [])
            with path.open("a") as stream:
                stream.write("\nnew\n")
            self.assertEqual(len(poller.poll()[1]["sbi"]), 1)

    def test_directory_inventory_failures_are_not_swallowed(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as folder:
            (Path(folder) / "nf.log").touch()
            poller = self.poller(folder)
            with patch.object(self.namespace["os"], "scandir", side_effect=PermissionError("secret path")):
                errors = poller.poll()[2]
            self.assertEqual(errors["sbi"], ["log_inventory_failed"])
            self.assertEqual(errors["pfcp"], ["log_inventory_failed"])

    def test_linux_read_failure_is_independent_of_successful_log_reads(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as folder:
            (Path(folder) / "known.log").touch()
            poller = self.poller(folder)
            with patch.dict(self.namespace, {"open": Mock(side_effect=PermissionError("secret"))}):
                linux, _, errors = poller.poll()
            self.assertEqual(linux, {})
            self.assertEqual(errors["linux"], ["linux_read_failed"])
            self.assertEqual(errors["sbi"], [])
            self.assertEqual(errors["pfcp"], [])

    def test_remote_sampling_uses_after_read_monotonic_clock_and_single_anchor(self):
        clock = SimpleNamespace(now=1_000_000_000)
        wall = datetime(2026, 10, 3, tzinfo=timezone.utc)
        now = Mock(return_value=wall)
        waits = []
        class Waiter:
            def wait(self, seconds):
                waits.append(seconds)
                clock.now += int(round(seconds * 1_000_000_000))
        class Collector:
            def __init__(self):
                raise AssertionError("collector construction forbidden")
            def _parse_line(self, line, path):
                self_test.assertTrue(self.run_id)
                self_test.assertEqual(path, "passive-cursor-log")
                return None
        self_test = self
        class Poller:
            def __init__(self, root, parsers, start):
                self.counts = dict.fromkeys(COUNTERS, 0)
                for parser in parsers.values():
                    parser("test log line")
            def poll(self):
                clock.now += 3_000_000
                self.counts["linux_event_count"] += 1
                return ({"load_1m": 0.1, "memory_total": 100, "memory_available": 40},
                        {"sbi": [], "pfcp": []}, {source: [] for source in ("linux", "sbi", "pfcp")})
        imports = Mock(side_effect=lambda name: SimpleNamespace(
            SBICollector=Collector, PFCPCollector=Collector,
            __file__=str(Path.home() / "free5gc" / "research" / "collectors" / (name.split(".")[-1] + ".py")),
        ))
        revision = Mock(return_value=SimpleNamespace(stdout="a" * 40))
        replacements = {
            "time": SimpleNamespace(time_ns=lambda: 5_000_000_000, monotonic_ns=lambda: clock.now),
            "datetime": SimpleNamespace(datetime=SimpleNamespace(now=now), timezone=timezone, timedelta=timedelta),
            "threading": SimpleNamespace(Event=Waiter), "socket": SimpleNamespace(gethostname=lambda: "fixture-host"),
            "importlib": SimpleNamespace(import_module=imports), "subprocess": SimpleNamespace(run=revision),
            "CursorPoller": Poller, "open": Mock(return_value=io.StringIO("11111111-1111-4111-8111-111111111111")),
            "select_log_root": Mock(return_value="fixture-log-run"),
            "parser_digest": Mock(return_value="b" * 64),
        }
        original_path = list(self.namespace["sys"].path)
        try:
            with patch.dict(self.namespace, replacements):
                capture = self.namespace["capture"](3, 10)
        finally:
            self.namespace["sys"].path[:] = original_path
        now.assert_called_once_with(timezone.utc)
        self.assertEqual(len(waits), 60)
        self.assertTrue(all(seconds > 0 for seconds in waits))
        self.assertEqual(capture["snapshots"][0]["monotonic_ns"], 1_003_000_000)
        self.assertEqual(capture["snapshots"][1]["monotonic_ns"], 2_006_000_000)
        self.assertEqual(revision.call_args.kwargs["timeout"], 5)
        self.assertEqual(imports.call_count, 2)
        self.assertEqual(process_capture(capture)["report"]["status"], "READY")


if __name__ == "__main__":
    unittest.main()