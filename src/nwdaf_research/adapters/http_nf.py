from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from nwdaf_research.policy.engine import PolicyDecision


class HTTPNFAdapter:
    """Call the separately deployed Ubuntu response-agent over HTTP."""

    def __init__(self, endpoint: str, api_key: str, timeout: float = 5.0):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def execute(self, decision: PolicyDecision) -> dict[str, Any]:
        if not decision.allowed:
            raise ValueError("cannot execute a rejected policy decision")
        payload = {
            "decisionId": decision.decision_id,
            "targetNF": decision.target_nf,
            "target": decision.target,
            "action": decision.action,
            "duration": decision.duration,
            "reason": decision.reason,
            "confidence": decision.confidence,
        }
        request = urllib.request.Request(
            f"{self.endpoint}/mitigation",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-API-Key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"response-agent rejected decision: {error.code} {body}") from error