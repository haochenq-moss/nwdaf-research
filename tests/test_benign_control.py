import ast
import importlib.util
import io
import json
import os
import shlex
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from nwdaf_research.input_testing.nrf_discovery import REQUEST_TARGET
from nwdaf_research.live import benign_control as control
from nwdaf_research.live import passive_campaign as passive
from nwdaf_research.live.ssh_observer import SSHLiveObserver
from test_passive_campaign import REPOSITORY, fault, valid_capture

REGISTERED = "33333333-3333-4333-8333-333333333333"


def namespace():
    result = {"__name__": "benign_fixture"}
    exec(compile(control.remote_prefix(REGISTERED) + passive.REMOTE_CODE, "<benign-fixture>", "exec"), result)
    return result


def benign_capture():
    capture = valid_capture()
    receipt = namespace()["benign_initialize"](3, 10, REGISTERED)["receipt"]
    receipt.update(auth_performed=True, performed=True, auth_status=200, http_status=200,
                   operation_start_monotonic_ns=42_000_000_000, operation_end_monotonic_ns=43_000_000_000,
                   discovery_start_monotonic_ns=42_200_000_000, discovery_end_monotonic_ns=42_800_000_000,
                   operation_error=None, worker_completed=True, warmup_admitted=True, trigger_index=41)
    capture.update(condition="benign_nrf", operation_receipt=receipt)
    return capture


class Response:
    def __init__(self, body, status=200):
        self.body = io.BytesIO(body)
        self.status = status
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.body.close()

    def isclosed(self):
        return self.body.closed

    def read1(self, size):
        self.read_sizes.append(size)
        return self.body.read(size)


class BenignControlTests(unittest.TestCase):
    def test_fixed_identity_and_safe_injection(self):
        import hashlib

        self.assertEqual(control.REQUEST_TARGET_SHA256, hashlib.sha256((REQUEST_TARGET + "\n").encode()).hexdigest())
        source = control.remote_prefix(REGISTERED) + passive.REMOTE_CODE
        ast.parse(source, feature_version=(3, 8))
        self.assertNotIn("sleep", source)
        self.assertNotIn("sudo", source)
        for value in (None, "bad", REGISTERED + "'; print('injected')", REGISTERED.upper(), True):
            if value == REGISTERED:
                continue
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError, AttributeError)):
                control.remote_prefix(value)

    def test_acquisition_condition_and_uuid_checked_before_executor(self):
        execute = Mock(return_value=SimpleNamespace(stdout=json.dumps(benign_capture())))
        capture = passive.acquire_capture(SSHLiveObserver(), window_count=3, duration_sec=10,
            condition="benign_nrf", registered_nf_instance_id=REGISTERED, execute=execute, execute_benign=True)
        self.assertEqual(capture["condition"], "benign_nrf")
        command = execute.call_args.args[0][-1]
        source = shlex.split(command)[2]
        self.assertIn("NF_INSTANCE_ID = " + repr(REGISTERED), source)
        self.assertIn("BENIGN_REQUEST_TARGET = " + repr(REQUEST_TARGET), source)
        for condition, identity, count, duration in (("unknown", REGISTERED, 3, 10), ("benign_nrf", "bad", 3, 10),
                                                    ("benign_nrf", REGISTERED, 1, 2), ("passive", REGISTERED, 3, 10)):
            execute.reset_mock()
            with self.subTest(condition=condition), self.assertRaises(ValueError):
                passive.acquire_capture(SSHLiveObserver(), window_count=count, duration_sec=duration,
                    condition=condition, registered_nf_instance_id=identity, execute=execute, execute_benign=True)
            execute.assert_not_called()

    def test_condition_mismatch_and_unexpected_receipt_fields_rejected(self):
        for capture in (valid_capture(), benign_capture()):
            if "condition" in capture:
                capture["operation_receipt"]["raw_headers"] = "secret"
            execute = Mock(return_value=SimpleNamespace(stdout=json.dumps(capture)))
            with self.assertRaises(passive.CaptureError):
                passive.acquire_capture(SSHLiveObserver(), window_count=3, duration_sec=10,
                    condition="benign_nrf", registered_nf_instance_id=REGISTERED, execute=execute, execute_benign=True)

    def test_valid_control_report_and_middle_boundaries(self):
        result = passive.process_capture(benign_capture())
        report = result["report"]
        self.assertEqual(report["status"], "READY")
        self.assertTrue(report["control_valid"])
        self.assertTrue(report["network_transmission_executed"])
        self.assertTrue(report["synchronized"])
        for window in result["windows"]:
            metadata = window["metadata"]
            self.assertEqual(metadata["declared_label"], "normal/benign_nrf")
            self.assertEqual(metadata["label_basis"], "declared_by_protocol_not_validated")
            self.assertEqual(metadata["middle_window_start_monotonic_ns"], 41_000_000_000)
            self.assertEqual(metadata["middle_window_end_monotonic_ns"], 51_000_000_000)

    def test_healthy_but_mistimed_or_failed_operation_invalid(self):
        cases = ({"http_status": 503, "operation_error": "HTTPError"},
                 {"discovery_end_monotonic_ns": 52_000_000_000, "operation_end_monotonic_ns": 52_000_000_000},
                 {"operation_start_monotonic_ns": 40_000_000_000},
                 {"operation_end_monotonic_ns": 47_000_000_000},
                 {"worker_completed": False, "operation_error": "WorkerTimeout"})
        for updates in cases:
            capture = benign_capture()
            capture["operation_receipt"].update(updates)
            with self.subTest(updates=updates):
                report = passive.process_capture(capture)["report"]
                self.assertEqual(report["collection_status"], "READY")
                self.assertEqual(report["status"], "CONTROL_INVALID")
                self.assertFalse(report["control_valid"])
                self.assertTrue(report["blockers"])

    def test_receipt_strict_types_secrets_and_contradictions_rejected(self):
        for updates in ({"performed": 1}, {"auth_status": True}, {"operation_error": "http://secret"},
                        {"request_identity": "POST anything"}, {"trigger_index": True},
                        {"discovery_start_monotonic_ns": -1}, {"auth_performed": False},
                        {"warmup_admitted": False}, {"discovery_end_monotonic_ns": None}):
            capture = benign_capture()
            capture["operation_receipt"].update(updates)
            with self.subTest(updates=updates), self.assertRaises(passive.CaptureError):
                passive.process_capture(capture)

    def test_manifest_has_no_passive_traffic_claims(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            path = Path(parent) / "benign"
            result = passive.run_campaign(path, condition="benign_nrf", registered_nf_instance_id=REGISTERED,
                execute=Mock(return_value=SimpleNamespace(stdout=json.dumps(benign_capture()))), execute_benign=True)
            self.assertEqual(result["status"], "READY")
            manifest = json.loads((path / "manifest.json").read_text())
            self.assertTrue(manifest["network_transmission_executed"])
            self.assertNotIn("No generated", manifest["network_transmission_scope"])
            self.assertTrue(manifest["control_valid"])

    def test_failed_warmup_preserves_capture_and_not_performed_receipt(self):
        capture = valid_capture()
        fault(capture, 3, "sbi")
        receipt = namespace()["benign_initialize"](3, 10, REGISTERED)["receipt"]
        receipt["operation_error"] = "WarmupNotReady"
        capture.update(condition="benign_nrf", operation_receipt=receipt)
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            target = Path(parent) / "benign"
            result = passive.run_campaign(target, condition="benign_nrf", registered_nf_instance_id=REGISTERED,
                execute=Mock(return_value=SimpleNamespace(stdout=json.dumps(capture))), execute_benign=True)
            self.assertEqual(result["status"], "CONTROL_INVALID")
            self.assertEqual(json.loads((target / "capture.json").read_text()), capture)
            report = json.loads((target / "report.json").read_text())
            self.assertFalse(report["network_transmission_executed"])
            self.assertEqual(report["generated_traffic_status"], "not_performed")

    def test_auth_only_failure_is_reported_as_generated_traffic(self):
        capture = benign_capture()
        capture["operation_receipt"].update(performed=False, discovery_start_monotonic_ns=None,
            discovery_end_monotonic_ns=None, http_status=None, auth_status=401, operation_error="HTTPError")
        report = passive.process_capture(capture)["report"]
        self.assertEqual(report["status"], "CONTROL_INVALID")
        self.assertTrue(report["network_transmission_executed"])
        self.assertEqual(report["generated_traffic_status"], "auth_attempted")

    def test_authorization_plan_pilot_and_identity_prechecks_no_writes(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            target = Path(parent) / "pair"
            execute = Mock()
            for updates in ({"execute_benign": False}, {"pair_id": 5}, {"pair_id": True},
                            {"registered_nf_instance_id": "not-uuid"}):
                kwargs = dict(pair_id=1, registered_nf_instance_id=REGISTERED, execute_benign=True, execute=execute)
                kwargs.update(updates)
                with self.subTest(updates=updates), self.assertRaises(ValueError):
                    control.run_pair(target, **kwargs)
            with patch.object(control, "PLAN_SHA256", "0" * 64), self.assertRaises(ValueError):
                control.run_pair(target, pair_id=1, registered_nf_instance_id=REGISTERED, execute_benign=True, execute=execute)
            self.assertFalse(target.exists())
            execute.assert_not_called()

    def test_low_level_benign_apis_require_explicit_authorization(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            target = Path(parent) / "benign"
            execute = Mock()
            for authorization in (False, 1, None):
                kwargs = dict(condition="benign_nrf", registered_nf_instance_id=REGISTERED,
                              execute=execute, execute_benign=authorization)
                with self.subTest(authorization=authorization), self.assertRaises(ValueError):
                    passive.acquire_capture(SSHLiveObserver(), window_count=3, duration_sec=10, **kwargs)
                with self.assertRaises(ValueError):
                    passive.run_campaign(target, **kwargs)
            self.assertEqual(list(Path(parent).iterdir()), [])
            execute.assert_not_called()

    def test_pair_order_journal_hashes_delta_and_no_real_subprocess(self):
        for pair_id, expected_order in ((1, ["passive", "benign_nrf"]), (2, ["benign_nrf", "passive"])):
            with self.subTest(pair_id=pair_id), tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
                target = Path(parent) / "pair"
                seen = []
                def execute(command, **kwargs):
                    condition = "benign_nrf" if "BENIGN_CONDITION =" in command[-1] else "passive"
                    journal = json.loads((target / "pair.json").read_text())
                    self.assertEqual(journal["current_condition"], condition)
                    self.assertEqual(journal["status"], "STARTED")
                    self.assertEqual((target / "frozen_plan.json").read_bytes(), control.PLAN_PATH.read_bytes())
                    seen.append(condition)
                    capture = benign_capture() if condition == "benign_nrf" else valid_capture()
                    return SimpleNamespace(stdout=json.dumps(capture))
                with patch("subprocess.run", side_effect=AssertionError("real subprocess forbidden")):
                    summary = control.run_pair(target, pair_id=pair_id, registered_nf_instance_id=REGISTERED,
                                               execute_benign=True, execute=execute)
                self.assertEqual(seen, expected_order)
                self.assertEqual(summary["executed_conditions"], expected_order)
                self.assertEqual(summary["status"], "READY")
                self.assertEqual(summary["middle_sbi_event_count_delta"], 0)
                self.assertEqual(summary["plan_sha256"], control.PLAN_SHA256)
                self.assertEqual(summary["split"], "pilot")
                self.assertFalse(summary["inference_performed"])
                self.assertFalse(summary["efficacy_claim"])
                for name in ("collector_module_sha256", "remote_code_sha256", "benign_remote_code_sha256"):
                    self.assertEqual(len(summary[name]), 64)
                self.assertEqual(json.loads((target / "pair_summary.json").read_text()), summary)
                retry = Mock()
                with self.assertRaises(FileExistsError):
                    control.run_pair(target, pair_id=pair_id, registered_nf_instance_id=REGISTERED,
                                     execute_benign=True, execute=retry)
                retry.assert_not_called()

    def test_pair_invalid_blocks_no_delta_and_passive_still_runs(self):
        for failure in ("http", "timing", "fixture", "transport", "parser_hash", "missing_parser_hash"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
                calls = []
                def execute(command, **kwargs):
                    condition = "benign_nrf" if "BENIGN_CONDITION =" in command[-1] else "passive"
                    calls.append(condition)
                    capture = benign_capture() if condition == "benign_nrf" else valid_capture()
                    if condition == "benign_nrf":
                        if failure == "transport":
                            raise RuntimeError("never persist this secret")
                        if failure == "http":
                            capture["operation_receipt"].update(http_status=500, operation_error="HTTPError")
                        if failure == "timing":
                            capture["operation_receipt"].update(discovery_end_monotonic_ns=52_000_000_000,
                                                                operation_end_monotonic_ns=52_000_000_000)
                        if failure == "fixture":
                            capture["git_revision"] = "b" * 40
                        if failure == "parser_hash":
                            capture["parser_sha256"]["sbi"] = "d" * 64
                        if failure == "missing_parser_hash":
                            del capture["parser_sha256"]
                    return SimpleNamespace(stdout=json.dumps(capture))
                target = Path(parent) / "pair"
                summary = control.run_pair(target, pair_id=2, registered_nf_instance_id=REGISTERED,
                                           execute_benign=True, execute=execute)
                self.assertEqual(calls, ["benign_nrf", "passive"])
                self.assertIn(summary["status"], ("CONTROL_INVALID", "INCOMPLETE"))
                self.assertIsNone(summary["middle_sbi_event_count_delta"])
                self.assertFalse(summary["control_valid"])
                self.assertTrue((target / "passive/capture.json").exists())
                self.assertNotIn("secret", (target / "pair.json").read_text())

    def test_final_acquisition_code_change_preserves_capture_but_withholds_delta(self):
        original = Path.read_bytes
        changed = False
        def read_bytes(path):
            if changed and path == Path(passive.__file__):
                return b"changed collector"
            return original(path)
        def execute(command, **kwargs):
            nonlocal changed
            benign = "BENIGN_CONDITION =" in command[-1]
            changed = benign
            return SimpleNamespace(stdout=json.dumps(benign_capture() if benign else valid_capture()))
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent, patch.object(Path, "read_bytes", read_bytes):
            target = Path(parent) / "pair"
            summary = control.run_pair(target, pair_id=1, registered_nf_instance_id=REGISTERED,
                                       execute_benign=True, execute=execute)
            self.assertEqual(summary["status"], "CONTROL_INVALID")
            self.assertIsNone(summary["middle_sbi_event_count_delta"])
            self.assertFalse(summary["outcomes"]["benign_nrf"]["provenance_verified"])
            self.assertTrue((target / "benign_nrf/capture.json").exists())

    def test_exact_transmitted_source_hash_is_verified_before_remote(self):
        execute = Mock(return_value=SimpleNamespace(stdout=json.dumps(valid_capture())))
        original = control.remote_prefix
        def prefix(registered):
            return original(registered) + ("\n" if execute.called else "")
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent, patch.object(control, "remote_prefix", prefix):
            summary = control.run_pair(Path(parent) / "pair", pair_id=1, registered_nf_instance_id=REGISTERED,
                                       execute_benign=True, execute=execute)
            execute.assert_called_once()
            self.assertEqual(summary["status"], "INCOMPLETE")
            self.assertIsNone(summary["middle_sbi_event_count_delta"])

    def test_interruption_preserves_completed_block_and_incomplete_journal(self):
        def execute(command, **kwargs):
            if "BENIGN_CONDITION =" in command[-1]:
                raise KeyboardInterrupt()
            return SimpleNamespace(stdout=json.dumps(valid_capture()))
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            target = Path(parent) / "pair"
            with self.assertRaises(KeyboardInterrupt):
                control.run_pair(target, pair_id=1, registered_nf_instance_id=REGISTERED,
                                 execute_benign=True, execute=execute)
            journal = json.loads((target / "pair.json").read_text())
            self.assertEqual(journal["status"], "INCOMPLETE")
            self.assertEqual(journal["error_type"], "KeyboardInterrupt")
            self.assertEqual(journal["executed_conditions"], ["passive"])
            self.assertTrue((target / "passive/capture.json").exists())

    def test_symlink_pair_parent_rejected_before_remote(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY) as parent:
            link = Path(parent) / "link"
            link.symlink_to(parent, target_is_directory=True)
            execute = Mock()
            with self.assertRaises(OSError):
                control.run_pair(link / "pair", pair_id=1, registered_nf_instance_id=REGISTERED,
                                 execute_benign=True, execute=execute)
            execute.assert_not_called()

    def test_cli_refuses_by_default_and_nonready_is_nonzero(self):
        spec = importlib.util.spec_from_file_location("benign_cli", REPOSITORY / "scripts/run_benign_control_pair.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        args = ["--pair-id", "1", "--pair-dir", str(REPOSITORY / "unused-pair"),
                "--registered-nf-instance-id", REGISTERED]
        with patch.object(cli, "run_pair") as run, patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.main(args)
            self.assertEqual(caught.exception.code, 2)
            run.assert_not_called()
        with patch.object(cli, "run_pair", return_value={"status": "CONTROL_INVALID"}), patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(cli.main([*args, "--execute-benign"]), 1)


class RemoteBenignTests(unittest.TestCase):
    def setUp(self):
        self.remote = namespace()

    def operation(self, responses):
        state = self.remote["benign_initialize"](3, 10, REGISTERED)
        state["receipt"].update(warmup_admitted=True, trigger_index=41)
        opener = Mock()
        opener.open.side_effect = responses
        build = Mock(return_value=opener)
        with patch.object(self.remote["urllib"].request, "build_opener", build):
            self.remote["benign_operation"](state)
        return state["receipt"], opener, build

    def test_exact_auth_and_one_get_bounded_discard_no_secrets(self):
        auth = Response(b'{"access_token":"fixture-secret-token"}')
        discovery = Response(b'{"fixture":"private-body"}')
        receipt, opener, build = self.operation([auth, discovery])
        control.validate_receipt(receipt)
        self.assertEqual(opener.open.call_count, 2)
        auth_request, get_request = [call.args[0] for call in opener.open.call_args_list]
        self.assertEqual(auth_request.full_url, "http://127.0.0.10:8000/oauth2/token")
        self.assertEqual(auth_request.method, "POST")
        self.assertEqual(urllib.parse.parse_qs(auth_request.data.decode()), {
            "grant_type": ["client_credentials"], "nfInstanceId": [REGISTERED], "nfType": ["AMF"],
            "targetNfType": ["NRF"], "scope": ["nnrf-disc"]})
        self.assertEqual(get_request.full_url, "http://127.0.0.10:8000" + REQUEST_TARGET)
        self.assertEqual(get_request.method, "GET")
        self.assertIsNone(get_request.data)
        self.assertEqual(get_request.headers["Authorization"], "Bearer fixture-secret-token")
        self.assertTrue(all(0 < call.kwargs["timeout"] <= 2 for call in opener.open.call_args_list))
        self.assertTrue(all(size <= 65536 for size in auth.read_sizes + discovery.read_sizes))
        self.assertIsNone(receipt["operation_error"])
        self.assertNotIn("fixture-secret-token", json.dumps(receipt))
        self.assertNotIn("private-body", json.dumps(receipt))
        self.assertTrue(any(isinstance(handler, self.remote["NoRedirect"]) for handler in build.call_args.args))
        self.assertIsNone(self.remote["NoRedirect"]().redirect_request(None, None, 302, "", {}, "http://other"))
        self.assertTrue(any(isinstance(handler, self.remote["DeadlineHTTPHandler"]) for handler in build.call_args.args))

    def test_auth_failures_suppress_get_and_never_retry(self):
        cases = [urllib.error.HTTPError("http://secret", 401, "secret", {}, None),
                 Response(b'{"access_token":null}'), Response(b"x" * 70000),
                 TimeoutError("secret timeout"), Response(b"not-json")]
        for response in cases:
            with self.subTest(response=type(response).__name__):
                receipt, opener, _ = self.operation([response])
                control.validate_receipt(receipt)
                self.assertTrue(receipt["auth_performed"])
                self.assertFalse(receipt["performed"])
                opener.open.assert_called_once()
                self.assertIsNotNone(receipt["operation_error"])
                self.assertNotIn("secret", json.dumps(receipt))

    def test_get_non2xx_read_limit_and_timeout_retained(self):
        for response in (urllib.error.HTTPError("http://secret", 503, "secret", {}, None),
                         Response(b"x" * 70000), TimeoutError("secret"), Response(b"", status=302)):
            with self.subTest(response=type(response).__name__):
                receipt, opener, _ = self.operation([Response(b'{"access_token":"token"}'), response])
                control.validate_receipt(receipt)
                self.assertTrue(receipt["performed"])
                self.assertEqual(opener.open.call_count, 2)
                self.assertIsNotNone(receipt["discovery_end_monotonic_ns"])
                self.assertIsNotNone(receipt["operation_error"])
                self.assertNotIn("secret", json.dumps(receipt))

    def test_deadline_remaining_and_socket_bound_without_network(self):
        with patch.dict(self.remote, {"time": SimpleNamespace(monotonic_ns=lambda: 1_000_000_000)}):
            self.assertEqual(self.remote["benign_remaining"](9_000_000_000), 2.0)
            self.assertEqual(self.remote["benign_remaining"](1_500_000_000), 0.5)
            with self.assertRaises(self.remote["OperationDeadline"]):
                self.remote["benign_remaining"](1_000_000_000)
        tree = ast.parse(control.REMOTE_BENIGN_CODE)
        socket_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DeadlineSocket")
        self.assertEqual({node.name for node in socket_class.body if isinstance(node, ast.FunctionDef)}, {"recv_into", "sendall"})

    def test_still_alive_receipt_is_honestly_failed_with_short_join(self):
        state = self.remote["benign_initialize"](3, 10, REGISTERED)
        state["worker"] = Mock()
        state["worker"].is_alive.return_value = True
        receipt = self.remote["benign_finish"](state)
        state["worker"].join.assert_called_once_with(timeout=0.1)
        self.assertEqual(receipt["operation_error"], "WorkerTimeout")
        self.assertFalse(receipt["worker_completed"])
        control.validate_receipt(receipt)

    def test_hook_once_after_actual_warmup_and_failed_warmup_suppressed(self):
        for mode in ("healthy", "fault", "short", "gap", "clock_age", "late_fault"):
            capture = valid_capture()
            if mode == "fault":
                fault(capture, 3, "sbi")
            if mode == "late_fault":
                fault(capture, 41, "pfcp")
            if mode == "short":
                capture["snapshots"][0]["monotonic_ns"] += 1
            if mode == "gap":
                capture["snapshots"][5]["monotonic_ns"] += 1_500_000_000
            state = self.remote["benign_initialize"](3, 10, REGISTERED)
            thread = Mock()
            thread.return_value.is_alive.return_value = False
            now = capture["snapshots"][30]["monotonic_ns"] + (3_000_000_000 if mode == "clock_age" else 0)
            with self.subTest(mode=mode), patch.dict(self.remote, {
                "threading": SimpleNamespace(Thread=thread), "time": SimpleNamespace(monotonic_ns=lambda: now)}):
                self.remote["benign_after_sample"](state, capture["snapshots"][:31],
                    capture["capture_errors"] if mode == "fault" else [])
                for index in (40, 41, 41, 42):
                    now = capture["snapshots"][index]["monotonic_ns"]
                    self.remote["benign_after_sample"](state, capture["snapshots"][:index + 1], capture["capture_errors"])
                if mode == "healthy":
                    thread.assert_called_once()
                    self.assertTrue(thread.call_args.kwargs["daemon"])
                    thread.return_value.start.assert_called_once()
                else:
                    thread.assert_not_called()
                    receipt = self.remote["benign_finish"](state)
                    self.assertFalse(receipt["performed"])
                    self.assertIsNotNone(receipt["operation_error"])
                    control.validate_receipt(receipt)

    def test_capture_worker_offthread_and_original_poll_cadence(self):
        clock = SimpleNamespace(now=1_000_000_000)
        waits = []
        completed = threading.Event()
        workers = []
        requests = []
        parent_thread = threading.get_ident()
        class Waiter:
            def wait(self, seconds):
                if workers:
                    self_test.assertTrue(completed.wait(timeout=2))
                waits.append(seconds)
                clock.now += int(round(seconds * 1_000_000_000))
        class Worker(threading.Thread):
            def __init__(self, target, args, daemon):
                def wrapped():
                    try:
                        target(*args)
                    finally:
                        completed.set()
                super().__init__(target=wrapped, daemon=daemon)
                workers.append(self)
        class Collector:
            def _parse_line(self, line, path):
                return None
        class Poller:
            def __init__(self, *args):
                self.counts = dict.fromkeys(passive.COUNTERS, 0)
            def poll(self):
                clock.now += 3_000_000
                self.counts["linux_event_count"] += 1
                return ({"load_1m": 0.1, "memory_total": 100, "memory_available": 40},
                        {"sbi": [], "pfcp": []}, {source: [] for source in passive.SOURCES})
        self_test = self
        def open_request(request, **kwargs):
            self.assertNotEqual(threading.get_ident(), parent_thread)
            requests.append((request.method, request.full_url))
            return Response(b'{"access_token":"token"}' if request.method == "POST" else b"discard")
        replacements = {
            "time": SimpleNamespace(time_ns=lambda: 5_000_000_000, monotonic_ns=lambda: clock.now),
            "threading": SimpleNamespace(Event=Waiter, Thread=Worker),
            "socket": SimpleNamespace(gethostname=lambda: "fixture-host"),
            "datetime": SimpleNamespace(datetime=SimpleNamespace(now=lambda zone: datetime(2026, 10, 3, tzinfo=timezone.utc)),
                                        timezone=timezone, timedelta=timedelta),
            "importlib": SimpleNamespace(import_module=lambda name: SimpleNamespace(
                SBICollector=Collector, PFCPCollector=Collector,
                __file__=str(Path.home() / "free5gc" / "research" / "collectors" / (name.split(".")[-1] + ".py")),
            )),
            "subprocess": SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(stdout="a" * 40)),
            "CursorPoller": Poller, "open": Mock(return_value=io.StringIO("11111111-1111-4111-8111-111111111111")),
            "select_log_root": lambda root: "fixture-log-run",
            "parser_digest": Mock(return_value="b" * 64),
        }
        original_path = list(self.remote["sys"].path)
        try:
            with patch.dict(self.remote, replacements), patch.object(self.remote["urllib"].request, "build_opener",
                    return_value=SimpleNamespace(open=open_request)):
                capture = self.remote["capture"](3, 10)
        finally:
            self.remote["sys"].path[:] = original_path
        self.assertEqual(len(workers), 1)
        self.assertEqual(requests, [("POST", "http://127.0.0.10:8000/oauth2/token"),
                                    ("GET", "http://127.0.0.10:8000" + REQUEST_TARGET)])
        self.assertEqual(len(waits), 60)
        self.assertTrue(all(seconds > 0 for seconds in waits))
        self.assertEqual(len(capture["snapshots"]), 61)
        self.assertEqual(passive.process_capture(capture)["report"]["status"], "READY")


if __name__ == "__main__":
    unittest.main()