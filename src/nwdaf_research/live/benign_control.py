from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable

from nwdaf_research.input_testing.nrf_discovery import REQUEST_TARGET

PLAN_PATH = Path(__file__).resolve().parents[3] / "configs/baseline_control_plan_v1.json"
PLAN_SHA256 = "1589f643ddd1bfcf5fd068c21f3d682ef5d6504242afc5d0883f1a3788b17b77"
REQUEST_TARGET_SHA256 = hashlib.sha256((REQUEST_TARGET + "\n").encode()).hexdigest()
REQUEST_IDENTITY = "GET " + REQUEST_TARGET + "; Authorization/token excluded"
OPERATION_ERRORS = {
    "WarmupNotReady", "HealthNotReady", "NotTriggered", "WorkerTimeout",
    "HTTPError", "URLError", "TimeoutError", "OSError", "ValueError",
    "InvalidToken", "BodyLimit", "OperationDeadline", "RemoteError",
}

REMOTE_BENIGN_CODE = r'''
import hashlib
import http.client
import socket
import urllib.error
import urllib.parse
import urllib.request

class InvalidToken(Exception):
    pass

class BodyLimit(Exception):
    pass

class OperationDeadline(Exception):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

def benign_initialize(window_count, duration_sec, registered):
    if (window_count, duration_sec) != (3, 10) or str(uuid.UUID(registered)) != registered:
        raise ValueError("invalid_benign_bounds")
    receipt = {
        "schema": "benign-nrf-receipt-v1", "method": "GET",
        "request_identity": "GET " + BENIGN_REQUEST_TARGET + "; Authorization/token excluded",
        "request_target_sha256": hashlib.sha256((BENIGN_REQUEST_TARGET + "\n").encode()).hexdigest(),
        "auth_performed": False, "performed": False, "auth_status": None, "http_status": None,
        "operation_start_monotonic_ns": None, "operation_end_monotonic_ns": None,
        "discovery_start_monotonic_ns": None, "discovery_end_monotonic_ns": None,
        "operation_error": "NotTriggered", "worker_completed": True,
        "warmup_admitted": False, "trigger_index": None,
    }
    return {"registered": registered, "receipt": receipt, "worker": None, "warmup": False}

def benign_healthy(snapshots, errors):
    if errors or not snapshots or not 0 <= time.monotonic_ns() - snapshots[-1]["monotonic_ns"] <= 2000000000:
        return False
    for index, row in enumerate(snapshots):
        for source in SOURCES:
            heartbeat = row["heartbeats"][source]
            if (row["poll_errors"][source] or not row["collectors"][source]["collector_healthy"]
                    or not row["collectors"][source]["telemetry_source_synced"]
                    or heartbeat["status"] != "HEALTHY" or heartbeat["metrics_summary"]["drops"] != 0
                    or heartbeat["timestamp_ns"] != row["monotonic_ns"]
                    or heartbeat["window_watermark_ns"] != row["monotonic_ns"]):
                return False
        if index:
            previous = snapshots[index - 1]
            if not 0 < row["monotonic_ns"] - previous["monotonic_ns"] <= 2000000000:
                return False
            if any(row["counters"][name] < previous["counters"][name] for name in COUNTERS):
                return False
            if row["counters"]["linux_event_count"] != previous["counters"]["linux_event_count"] + 1:
                return False
    return True

def benign_remaining(deadline):
    remaining = (deadline - time.monotonic_ns()) / 1000000000
    if remaining <= 0:
        raise OperationDeadline()
    return min(2.0, remaining)

class DeadlineSocket(socket.socket):
    def recv_into(self, buffer, *args):
        self.settimeout(benign_remaining(self.deadline))
        return super().recv_into(buffer, *args)

    def sendall(self, data, *args):
        self.settimeout(benign_remaining(self.deadline))
        return super().sendall(data, *args)

class DeadlineConnection(http.client.HTTPConnection):
    def connect(self):
        super().connect()
        self.sock = DeadlineSocket(fileno=self.sock.detach())
        self.sock.deadline = self.operation_deadline

class DeadlineHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, deadline):
        super().__init__()
        self.deadline = deadline

    def http_open(self, request):
        def connection(host, **kwargs):
            result = DeadlineConnection(host, **kwargs)
            result.operation_deadline = self.deadline
            return result
        return self.do_open(connection, request)

def benign_read(response, deadline):
    body = bytearray()
    while len(body) < 65536:
        benign_remaining(deadline)
        if response.isclosed():
            return bytes(body)
        chunk = response.read1(min(4096, 65536 - len(body)))
        benign_remaining(deadline)
        if not chunk:
            return bytes(body)
        body.extend(chunk)
    raise BodyLimit()

def benign_operation(state):
    receipt = state["receipt"]
    receipt["operation_start_monotonic_ns"] = time.monotonic_ns()
    deadline = receipt["operation_start_monotonic_ns"] + 4500000000
    token = None
    request = None
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), DeadlineHTTPHandler(deadline))
        request = urllib.request.Request("http://127.0.0.10:8000/oauth2/token",
            data=urllib.parse.urlencode({"grant_type": "client_credentials", "nfInstanceId": state["registered"],
                "nfType": "AMF", "targetNfType": "NRF", "scope": "nnrf-disc"}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        receipt["auth_performed"] = True
        with opener.open(request, timeout=benign_remaining(deadline)) as response:
            receipt["auth_status"] = response.status
            if not 200 <= response.status < 300:
                raise urllib.error.HTTPError(request.full_url, response.status, "", {}, None)
            payload = json.loads(benign_read(response, deadline))
            token = payload.get("access_token") if isinstance(payload, dict) else None
            del payload
            if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9._~+/-]{1,16384}=*", token):
                raise InvalidToken()
        benign_remaining(deadline)
        request = urllib.request.Request("http://127.0.0.10:8000" + BENIGN_REQUEST_TARGET,
            headers={"Authorization": "Bearer " + token}, method="GET")
        receipt["discovery_start_monotonic_ns"] = time.monotonic_ns()
        receipt["performed"] = True
        try:
            with opener.open(request, timeout=benign_remaining(deadline)) as response:
                receipt["http_status"] = response.status
                if not 200 <= response.status < 300:
                    raise urllib.error.HTTPError(request.full_url, response.status, "", {}, None)
                benign_read(response, deadline)
        finally:
            receipt["discovery_end_monotonic_ns"] = time.monotonic_ns()
        benign_remaining(deadline)
        receipt["operation_error"] = None
    except urllib.error.HTTPError as error:
        receipt["http_status" if receipt["performed"] else "auth_status"] = error.code
        receipt["operation_error"] = "HTTPError"
        error.close()
    except Exception as error:
        name = type(error).__name__
        receipt["operation_error"] = name if name in BENIGN_ERROR_TYPES else "RemoteError"
    finally:
        del token
        del request
        receipt["operation_end_monotonic_ns"] = time.monotonic_ns()
        if receipt["operation_end_monotonic_ns"] > deadline:
            receipt["operation_error"] = "OperationDeadline"
        receipt["worker_completed"] = True

def benign_after_sample(state, snapshots, errors):
    index = snapshots[-1]["index"]
    if index == 30:
        state["warmup"] = (len(snapshots) == 31 and benign_healthy(snapshots, errors)
            and snapshots[30]["monotonic_ns"] - snapshots[0]["monotonic_ns"] >= 30000000000)
        state["receipt"]["warmup_admitted"] = state["warmup"]
        if not state["warmup"]:
            state["receipt"]["operation_error"] = "WarmupNotReady"
    if index == 41 and state["warmup"] and state["worker"] is None:
        if not benign_healthy(snapshots, errors):
            state["receipt"]["operation_error"] = "HealthNotReady"
            return
        state["receipt"].update(trigger_index=41, worker_completed=False)
        state["worker"] = threading.Thread(target=benign_operation, args=(state,), daemon=True)
        state["worker"].start()

def benign_finish(state):
    worker = state["worker"]
    if worker is not None:
        worker.join(timeout=0.1)
    receipt = dict(state["receipt"])
    if worker is not None and worker.is_alive():
        receipt.update(worker_completed=False, operation_error="WorkerTimeout")
    return receipt
'''


def validate_nf_instance_id(value: str) -> str:
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("registered_nf_instance_id must be a canonical UUID")
    return value


def remote_prefix(registered_nf_instance_id: str) -> str:
    registered = validate_nf_instance_id(registered_nf_instance_id)
    return (f"BENIGN_CONDITION = 'benign_nrf'\nNF_INSTANCE_ID = {registered!r}\n"
            f"BENIGN_REQUEST_TARGET = {REQUEST_TARGET!r}\nBENIGN_ERROR_TYPES = {sorted(OPERATION_ERRORS)!r}\n"
            + REMOTE_BENIGN_CODE + "\n")


def validate_receipt(receipt: Any) -> None:
    keys = {"schema", "method", "request_identity", "request_target_sha256", "auth_performed", "performed",
            "auth_status", "http_status", "operation_start_monotonic_ns", "operation_end_monotonic_ns",
            "discovery_start_monotonic_ns", "discovery_end_monotonic_ns", "operation_error",
            "worker_completed", "warmup_admitted", "trigger_index"}
    if not isinstance(receipt, dict) or set(receipt) != keys:
        raise ValueError("invalid operation receipt fields")
    expected = {"schema": "benign-nrf-receipt-v1", "method": "GET", "request_identity": REQUEST_IDENTITY,
                "request_target_sha256": REQUEST_TARGET_SHA256}
    if any(receipt[name] != value for name, value in expected.items()):
        raise ValueError("invalid fixed request identity")
    for name in ("auth_performed", "performed", "worker_completed", "warmup_admitted"):
        if type(receipt[name]) is not bool:
            raise ValueError("invalid receipt flag")
    for name in ("auth_status", "http_status"):
        if receipt[name] is not None and (type(receipt[name]) is not int or not 100 <= receipt[name] <= 599):
            raise ValueError("invalid receipt HTTP status")
    for name in keys:
        if name.endswith("_monotonic_ns") and receipt[name] is not None:
            if type(receipt[name]) is not int or receipt[name] < 0:
                raise ValueError("invalid receipt timestamp")
    if receipt["operation_error"] is not None and receipt["operation_error"] not in OPERATION_ERRORS:
        raise ValueError("invalid operation error type")
    if receipt["trigger_index"] is not None and (type(receipt["trigger_index"]) is not int or receipt["trigger_index"] != 41):
        raise ValueError("invalid trigger index")
    if receipt["performed"] and not receipt["auth_performed"]:
        raise ValueError("discovery without auth attempt")
    for flag, start, end, status in (
        ("auth_performed", "operation_start_monotonic_ns", "operation_end_monotonic_ns", "auth_status"),
        ("performed", "discovery_start_monotonic_ns", "discovery_end_monotonic_ns", "http_status"),
    ):
        if receipt[flag] and receipt[start] is None:
            raise ValueError("attempt without start receipt")
        inactive_fields = (start, end, status) if flag == "performed" else (status,)
        if not receipt[flag] and any(receipt[name] is not None for name in inactive_fields):
            raise ValueError("unperformed operation has activity receipt")
        if receipt[end] is not None and (receipt[start] is None or receipt[end] < receipt[start]):
            raise ValueError("invalid operation chronology")
        if receipt[flag] and receipt["worker_completed"] and receipt[end] is None:
            raise ValueError("completed attempt without end receipt")
    if receipt["trigger_index"] is None and (receipt["auth_performed"] or receipt["operation_start_monotonic_ns"] is not None):
        raise ValueError("operation without trigger receipt")
    if receipt["trigger_index"] is not None and not receipt["warmup_admitted"]:
        raise ValueError("trigger without warmup admission")
    if receipt["operation_error"] is None and (not receipt["performed"] or not receipt["worker_completed"]):
        raise ValueError("success without completed discovery")


def extend_processed(capture: dict[str, Any], processed: dict[str, Any]) -> None:
    receipt = capture["operation_receipt"]
    report = processed["report"]
    middle = processed["windows"][1]["metadata"]
    start, end = middle["start_monotonic_ns"], middle["end_monotonic_ns"]
    blockers = []
    if not receipt["warmup_admitted"] or report["warmup"]["status"] != "READY":
        blockers.append("benign warmup not admitted")
    if not receipt["performed"] or not receipt["auth_performed"]:
        blockers.append("fixed discovery not performed")
    if not receipt["worker_completed"] or receipt["operation_error"] is not None:
        blockers.append("benign operation failed or incomplete")
    if any(receipt[name] is None or not 200 <= receipt[name] < 300 for name in ("auth_status", "http_status")):
        blockers.append("benign HTTP status not successful")
    times = [receipt[name] for name in ("operation_start_monotonic_ns", "discovery_start_monotonic_ns",
                                      "discovery_end_monotonic_ns", "operation_end_monotonic_ns")]
    synchronized = (start is not None and end is not None and all(value is not None for value in times)
                    and start <= times[0] <= times[1] <= times[2] <= times[3] <= end
                    and times[3] - times[0] <= 4_500_000_000
                    and len(capture["snapshots"]) > 41 and times[0] >= capture["snapshots"][41]["monotonic_ns"]
                    and receipt["trigger_index"] == 41)
    if not synchronized:
        blockers.append("benign operation outside synchronized middle window or deadline")
    valid = report["status"] == "READY" and not blockers
    report.update(condition="benign_nrf", operation_receipt=receipt, control_valid=valid,
                  collection_status=report["status"], synchronized=bool(synchronized),
                  middle_window_start_monotonic_ns=start, middle_window_end_monotonic_ns=end,
                  network_transmission_executed=receipt["auth_performed"] or receipt["performed"],
                  generated_traffic_status="discovery_attempted" if receipt["performed"] else (
                      "auth_attempted" if receipt["auth_performed"] else "not_performed"),
                  operation_scope="Fixed OAuth and one fixed read-only NRF discovery only; active UE not modified; continuity not verified.")
    if not valid:
        report["status"] = "CONTROL_INVALID"
    report["blockers"] = sorted(set(report["blockers"] + blockers))
    for window in processed["windows"]:
        window["metadata"].update(condition="benign_nrf", declared_label="normal/benign_nrf",
                                  control_valid=valid, operation_receipt=receipt,
                                  middle_window_start_monotonic_ns=start, middle_window_end_monotonic_ns=end)


def _write_json(directory_fd: int, name: str, document: Any, *, replace: bool = False) -> None:
    target = ".pair-next.json" if replace else name
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        os.replace(target, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    os.fsync(directory_fd)


def validate_held_out_authorization(path: str | Path, *, pair_id: int, registered: str) -> dict[str, str]:
    content = Path(path).read_bytes()
    authorization = json.loads(content)
    if not isinstance(authorization, dict) or authorization.get("schema_version") != "benign-held-out-authorization-v1":
        raise ValueError("invalid held-out authorization")
    if authorization.get("plan_sha256") != PLAN_SHA256 or authorization.get("registered_nf_instance_id") != registered:
        raise ValueError("authorization plan or registered target mismatch")
    allowed = authorization.get("allowed_pair_ids")
    if not isinstance(allowed, list) or any(type(value) is not int or value not in range(5, 13) for value in allowed) or pair_id not in allowed:
        raise ValueError("pair not authorized")
    if authorization.get("held_out_collection_authorized") is not True or any(
        authorization.get(name) is not False for name in (
            "inference_authorized", "model_deployment_authorized", "network_enforcement_authorized",
        )
    ):
        raise ValueError("held-out collection requires disabled inference and enforcement")
    if authorization.get("response_scope") != "operator_alert_only":
        raise ValueError("response scope must be alert-only")
    return {"authorization_sha256": hashlib.sha256(content).hexdigest(), "authorization_scope": "held_out_benign_collection_only"}


def run_pair(pair_dir: str | Path, *, pair_id: int, registered_nf_instance_id: str,
             execute_benign: bool = False, observer: Any = None,
             execute: Callable[..., Any] | None = None,
             authorization_path: str | Path | None = None) -> dict[str, Any]:
    if execute_benign is not True:
        raise ValueError("explicit execute_benign=True authorization required")
    if type(pair_id) is not int or not 1 <= pair_id <= 12:
        raise ValueError("pair ID must be 1 through 12")
    registered = validate_nf_instance_id(registered_nf_instance_id)
    authorization = {}
    if pair_id >= 5:
        if authorization_path is None:
            raise ValueError("held-out pairs require separate scoped authorization")
        authorization = validate_held_out_authorization(authorization_path, pair_id=pair_id, registered=registered)
    frozen = PLAN_PATH.read_bytes()
    if hashlib.sha256(frozen).hexdigest() != PLAN_SHA256:
        raise ValueError("frozen plan SHA256 mismatch")
    plan = json.loads(frozen)
    from nwdaf_research.live import passive_campaign

    hashes = {
        "collector_module_sha256": hashlib.sha256(Path(passive_campaign.__file__).read_bytes()).hexdigest(),
        "control_module_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "remote_code_sha256": hashlib.sha256(passive_campaign.REMOTE_CODE.encode()).hexdigest(),
        "benign_remote_code_sha256": hashlib.sha256((remote_prefix(registered) + passive_campaign.REMOTE_CODE).encode()).hexdigest(),
    }
    def code_unchanged():
        return (hashlib.sha256(Path(passive_campaign.__file__).read_bytes()).hexdigest() == hashes["collector_module_sha256"]
                and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == hashes["control_module_sha256"])

    first = plan["schedule"]["first_condition"][pair_id - 1]
    order = [first, "benign_nrf" if first == "passive" else "passive"]
    destination, parent_fd = passive_campaign._parent_descriptor(pair_dir)
    directory_fd = None
    partition = "pilot" if pair_id <= 4 else "held_out"
    journal = {"schema": "benign-control-pair-v1", "pair_id": pair_id, "group": f"{partition}-pair-{pair_id:02d}",
               "split": partition, "attempt_id": str(uuid.uuid4()), "plan_sha256": PLAN_SHA256,
               **authorization,
               **hashes, "registered_nf_instance_id": registered, "condition_order": order,
               "status": "STARTED", "executed_conditions": [], "outcomes": {}, "error_type": None}
    try:
        os.mkdir(destination.name, mode=0o700, dir_fd=parent_fd)
        directory_fd = os.open(destination.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        descriptor = os.open("frozen_plan.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(frozen)
            stream.flush()
            os.fsync(stream.fileno())
        _write_json(directory_fd, "pair.json", journal)
        os.fsync(parent_fd)
        for condition in order:
            journal["current_condition"] = condition
            _write_json(directory_fd, "pair.json", journal, replace=True)
            try:
                if not code_unchanged():
                    raise ValueError("collector changed during pair")
                def execute_block(command, **kwargs):
                    source = shlex.split(command[-1])[2]
                    key = "benign_remote_code_sha256" if condition == "benign_nrf" else "remote_code_sha256"
                    if hashlib.sha256(source.encode()).hexdigest() != hashes[key]:
                        raise ValueError("transmitted collector source changed")
                    return (execute or subprocess.run)(command, **kwargs)

                outcome = passive_campaign.run_campaign(destination / condition, window_count=3, duration_sec=10,
                    observer=observer, execute=execute_block, condition=condition,
                    registered_nf_instance_id=registered if condition == "benign_nrf" else None,
                    execute_benign=execute_benign)
                outcome.update(condition=condition, provenance_verified=code_unchanged(),
                    collector_module_sha256=hashes["collector_module_sha256"],
                    remote_code_sha256=hashes["benign_remote_code_sha256" if condition == "benign_nrf" else "remote_code_sha256"])
                journal["outcomes"][condition] = outcome
            except Exception as error:
                journal["outcomes"][condition] = {"status": "INCOMPLETE", "error_type": type(error).__name__}
                journal["error_type"] = type(error).__name__
            journal["executed_conditions"].append(condition)
            _write_json(directory_fd, "pair.json", journal, replace=True)
        blockers = []
        if any(value["status"] != "READY" for value in journal["outcomes"].values()):
            blockers.append("both matched blocks must be READY and benign control valid")
        if not all(value.get("provenance_verified", False) for value in journal["outcomes"].values()):
            blockers.append("collector code provenance changed or unverified")
        documents = {}
        for condition in order:
            folder = destination / condition
            if journal["outcomes"][condition]["status"] != "INCOMPLETE":
                documents[condition] = {
                    "manifest": json.loads((folder / "manifest.json").read_text()),
                    "report": json.loads((folder / "report.json").read_text()),
                    "middle": json.loads((folder / "windows/WBASE002/readiness.json").read_text()),
                }
        if len(documents) == 2:
            passive, benign = documents["passive"], documents["benign_nrf"]
            fixture_keys = ("hostname", "boot_id", "git_revision", "parser_paths", "contract", "clock_domain",
                            "warmup_sec", "window_count", "nominal_duration_sec", "read_budget")
            if any(passive["manifest"][key] != benign["manifest"][key] for key in fixture_keys):
                blockers.append("matched fixture or collection provenance mismatch")
            parser_hashes = passive["manifest"].get("parser_sha256", {})
            if set(parser_hashes) != {"sbi", "pfcp"} or parser_hashes != benign["manifest"].get("parser_sha256"):
                blockers.append("remote parser file hashes missing or mismatched")
            if not benign["report"].get("control_valid"):
                blockers.append("benign synchronization or operation invalid")
        valid = not blockers and len(documents) == 2
        delta = (documents["benign_nrf"]["middle"]["features"]["sbi_event_count"]
                 - documents["passive"]["middle"]["features"]["sbi_event_count"]) if valid else None
        journal["status"] = "INCOMPLETE" if journal["error_type"] else ("READY" if valid else "CONTROL_INVALID")
        journal.pop("current_condition", None)
        _write_json(directory_fd, "pair.json", journal, replace=True)
        summary = {**journal, "control_valid": valid, "blockers": blockers,
                   "middle_sbi_event_count_delta": delta, "inference_performed": False,
                   "label_basis": "declared_by_protocol_not_validated", "efficacy_claim": False}
        _write_json(directory_fd, "pair_summary.json", summary)
        return summary
    except BaseException as error:
        if directory_fd is not None:
            journal.update(status="INCOMPLETE", error_type=type(error).__name__)
            _write_json(directory_fd, "pair.json", journal, replace=True)
        raise
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        os.close(parent_fd)