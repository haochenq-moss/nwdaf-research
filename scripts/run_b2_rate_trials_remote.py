#!/usr/bin/env python3
"""Run bounded rate-limit trials on Ubuntu using its protected agent key."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone


def qdisc() -> str:
    return subprocess.run(
        ["tc", "qdisc", "show", "dev", "ueTun0"], capture_output=True, text=True
    ).stdout.strip()


def ping() -> dict[str, float | None]:
    output = subprocess.run(
        ["ping", "-I", "ueTun0", "-c", "2", "-W", "1", "10.60.0.1"],
        capture_output=True, text=True,
    ).stdout
    loss = None
    rtt = None
    for line in output.splitlines():
        if "packet loss" in line:
            loss = float(line.split("%", 1)[0].split()[-1])
        if "rtt" in line or "round-trip" in line:
            rtt = float(line.split("=", 1)[1].split("/", 2)[1])
    return {"packet_loss_percent": loss, "rtt_mean_ms": rtt}


def main() -> None:
    api_key = os.environ["RESPONSE_AGENT_API_KEY"]
    results = []
    for index in range(1, 11):
        decision_id = f"tc-paper-trial-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{index:02d}"
        before = qdisc()
        payload = {
            "decisionId": decision_id,
            "targetNF": "SMF",
            "target": {"interface": "ueTun0"},
            "action": "rate_limit",
            "duration": 1,
            "reason": "paper_repeat_rate_limit_trial",
            "confidence": 0.95,
        }
        request = urllib.request.Request(
            "http://127.0.0.1:9090/mitigation",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-API-Key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = json.loads(response.read().decode())
                status = response.status
        except Exception as error:
            body = {"error": str(error)}
            status = 0
        during = qdisc()
        network = ping()
        after = qdisc()
        results.append({
            "trial": index,
            "decision_id": decision_id,
            "http_status": status,
            "response": body,
            "qdisc_before": before,
            "qdisc_during": during,
            "qdisc_after": after,
            "network": network,
        })
        print(json.dumps(results[-1]), flush=True)


if __name__ == "__main__":
    main()