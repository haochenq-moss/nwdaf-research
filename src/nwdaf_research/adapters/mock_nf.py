from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from nwdaf_research.policy.engine import PolicyDecision


@dataclass
class MockNF:
    name: str
    reactions: list[dict[str, Any]] = field(default_factory=list)

    def handle_mitigation(self, decision: PolicyDecision) -> dict[str, Any]:
        reaction = {
            "decision_id": decision.decision_id,
            "nf": self.name,
            "action": decision.action,
            "target": decision.target,
            "duration": decision.duration,
            "status": "applied",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.reactions.append(reaction)
        return reaction


class MockNFAdapter:
    """In-memory adapter; it performs no process, network, or shell execution."""

    def __init__(self):
        self.nfs = {name: MockNF(name) for name in ("AMF", "SMF", "PCF")}

    def execute(self, decision: PolicyDecision) -> dict[str, Any]:
        if not decision.allowed:
            raise ValueError("cannot execute a rejected policy decision")
        nf = self.nfs.get(decision.target_nf)
        if nf is None:
            raise ValueError(f"no adapter registered for {decision.target_nf}")
        return nf.handle_mitigation(decision)