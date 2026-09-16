#!/usr/bin/env python3
"""Controlled Ubuntu-side response agent for the external analytics prototype.

The agent uses only the Python standard library so it can run on Ubuntu 20.04.
By default, alert_operator is the only applied action. Network shaping is
disabled unless explicitly enabled and a non-interactive sudo tc command works.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResponseStore:
    def __init__(self, database_path: Path, audit_path: Path):
        self.database_path = database_path
        self.audit_path = audit_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS decisions (decision_id TEXT PRIMARY KEY, created_at TEXT NOT NULL)"
            )
            connection.commit()

    def claim(self, decision_id: str) -> bool:
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute(
                    "INSERT INTO decisions(decision_id, created_at) VALUES (?, ?)",
                    (decision_id, utc_now()),
                )
                connection.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def audit(self, event: dict[str, Any]) -> None:
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"timestamp": utc_now(), **event}, sort_keys=True) + "\n")


class AgentHandler(BaseHTTPRequestHandler):
    server_version = "NWDAFResponseAgent/0.1"

    def _json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"status": "ok", "service": "ubuntu-response-agent"})
            return
        self._json(404, {"status": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/mitigation":
            self._json(404, {"status": "not_found"})
            return
        expected_key = self.server.api_key
        supplied_key = self.headers.get("X-API-Key", "")
        if not expected_key or supplied_key != expected_key:
            self._json(401, {"status": "rejected", "reason": "invalid API key"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            decision_id = str(request["decisionId"])
            target_nf = str(request["targetNF"])
            target = request["target"]
            action = str(request["action"])
            duration = request.get("duration")
            confidence = float(request["confidence"])
            reason = str(request["reason"])
            if not isinstance(target, dict) or not target:
                raise ValueError("target must be a non-empty object")
            if not self.server.store.claim(decision_id):
                self._json(409, {"status": "rejected", "reason": "decisionId replay"})
                return
            if confidence < self.server.minimum_confidence:
                self._reject(request, "confidence below threshold")
                return
            if target_nf not in {"AMF", "SMF", "PCF"}:
                self._reject(request, "unsupported target NF")
                return
            result = self._apply(
                decision_id, target_nf, target, action, duration, confidence, reason
            )
            self._json(200 if result["status"] == "accepted" else 422, result)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._json(400, {"status": "rejected", "reason": str(error)})

    def _reject(self, request: dict[str, Any], reason: str) -> None:
        result = {"status": "rejected", "decisionId": request.get("decisionId"), "reason": reason}
        self.server.store.audit({"event": "mitigation_rejected", **result})
        self._json(422, result)

    def _apply(
        self,
        decision_id: str,
        target_nf: str,
        target: dict[str, Any],
        action: str,
        duration: Any,
        confidence: float,
        reason: str,
    ) -> dict[str, Any]:
        base = {
            "decisionId": decision_id,
            "targetNF": target_nf,
            "action": action,
        }
        if action == "alert_operator":
            result = {"status": "accepted", **base, "effect": "audit_alert_recorded"}
            self.server.store.audit(
                {"event": "alert_operator", **result, "target": target, "reason": reason}
            )
            return result
        if action == "rate_limit":
            if not self.server.enable_live_actions:
                result = {"status": "rejected", **base, "reason": "live actions disabled"}
                self.server.store.audit({"event": "mitigation_rejected", **result})
                return result
            if target.get("interface") != self.server.allowed_interface:
                result = {"status": "rejected", **base, "reason": "interface not allow-listed"}
                self.server.store.audit({"event": "mitigation_rejected", **result})
                return result
            if duration is None or int(duration) < 1 or int(duration) > 60:
                result = {"status": "rejected", **base, "reason": "duration must be 1..60 seconds"}
                self.server.store.audit({"event": "mitigation_rejected", **result})
                return result
            command = [
                "sudo",
                "-n",
                "/usr/sbin/tc",
                "qdisc",
                "replace",
                "dev",
                self.server.allowed_interface,
                "root",
                "tbf",
                "rate",
                "1mbit",
                "burst",
                "32kbit",
                "latency",
                "400ms",
            ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=5)
            if completed.returncode != 0:
                result = {"status": "rejected", **base, "reason": "sudo tc action unavailable"}
                self.server.store.audit({"event": "mitigation_rejected", **result})
                return result
            timer = threading.Timer(
                int(duration), self.server.restore_interface, args=(decision_id,)
            )
            timer.daemon = True
            timer.start()
            result = {"status": "accepted", **base, "effect": "tc_rate_limit_applied"}
            self.server.store.audit({"event": "mitigation_applied", **result, "target": target})
            return result
        result = {"status": "rejected", **base, "reason": "action disabled or unsupported"}
        self.server.store.audit({"event": "mitigation_rejected", **result})
        return result

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9090)
    parser.add_argument("--api-key", default=os.environ.get("RESPONSE_AGENT_API_KEY"))
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".nwdaf-response-agent")
    parser.add_argument("--enable-live-actions", action="store_true")
    parser.add_argument("--interface", default="ueTun0")
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("RESPONSE_AGENT_API_KEY or --api-key is required")
    store = ResponseStore(args.state_dir / "decisions.sqlite3", args.state_dir / "audit.jsonl")
    server = ThreadingHTTPServer((args.host, args.port), AgentHandler)
    server.api_key = args.api_key
    server.store = store
    server.minimum_confidence = 0.8
    server.enable_live_actions = args.enable_live_actions
    server.allowed_interface = args.interface

    def restore_interface(decision_id: str) -> None:
        command = [
            "sudo",
            "-n",
            "/usr/sbin/tc",
            "qdisc",
            "replace",
            "dev",
            args.interface,
            "root",
            "fq_codel",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=5)
        server.store.audit(
            {
                "event": "tc_rate_limit_restored",
                "decisionId": decision_id,
                "status": "restored" if completed.returncode == 0 else "restore_failed",
            }
        )

    server.restore_interface = restore_interface
    print(json.dumps({"status": "listening", "host": args.host, "port": args.port, "live_actions": args.enable_live_actions}))
    server.serve_forever()


if __name__ == "__main__":
    main()