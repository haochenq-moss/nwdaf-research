from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
from typing import Any, Callable

from nwdaf_research.adapters.mock_nf import MockNFAdapter
from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer
from nwdaf_research.policy.engine import PolicyEngine

from .verification import ResponseVerifier


class ClosedLoopController:
    """Coordinate one policy-bounded detect, react, and verify cycle."""

    def __init__(
        self,
        analytics: NWDAFResearchAnalyzer,
        policy: PolicyEngine,
        adapter: MockNFAdapter,
        verifier: ResponseVerifier | None = None,
    ):
        self.analytics = analytics
        self.policy = policy
        self.adapter = adapter
        self.verifier = verifier or ResponseVerifier()
        self.audit_log: list[dict[str, Any]] = []

    def observe(self, features: dict[str, float]) -> dict[str, float]:
        return {key: float(value) for key, value in features.items()}

    def run(
        self,
        *,
        run_id: str,
        decision_id: str,
        target_nf: str,
        target: dict[str, str],
        action: str,
        reason: str,
        observation: dict[str, float],
        after_observe: Callable[[], dict[str, float]] | None = None,
        duration: int | None = None,
    ) -> dict[str, Any]:
        observed = self.observe(observation)
        detection_timestamp = datetime.now(timezone.utc).isoformat()
        detection = self.analytics.score_features(observed)
        decision = self.policy.evaluate(
            decision_id=decision_id,
            target_nf=target_nf,
            target=target,
            action=action,
            duration=duration,
            reason=reason,
            confidence=float(detection["confidence"]),
        )
        if detection["predicted_label"] == "NORMAL":
            decision = replace(
                decision,
                allowed=False,
                rejection_reason="analytics classified observation as normal",
            )
        event: dict[str, Any] = {
            "run_id": run_id,
            "decision_id": decision_id,
            "detection_timestamp": detection_timestamp,
            "attack_type": reason,
            "detection": detection,
            "decision": {
                "allowed": decision.allowed,
                "action": decision.action,
                "rejection_reason": decision.rejection_reason,
            },
        }
        if not decision.allowed:
            event["response"] = {"status": "rejected"}
            event["verification"] = self.verifier.verify(
                before=observed,
                after=None,
                anomaly_score_before=float(detection["anomaly_probability"]),
                anomaly_score_after=None,
            )
            self.audit_log.append(event)
            return event

        response_timestamp = datetime.now(timezone.utc).isoformat()
        response = self.adapter.execute(decision)
        event["response"] = {"status": "applied", "details": response}
        event["response_timestamp"] = response_timestamp
        after = after_observe() if after_observe is not None else None
        after_score = None
        if after is not None:
            after_score = float(
                self.analytics.score_features(self.observe(after))["anomaly_probability"]
            )
        event["verification"] = self.verifier.verify(
            before=observed,
            after=after,
            anomaly_score_before=float(detection["anomaly_probability"]),
            anomaly_score_after=after_score,
        )
        event["verification_timestamp"] = datetime.now(timezone.utc).isoformat()
        self.audit_log.append(event)
        return event