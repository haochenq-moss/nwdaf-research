from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PolicyDecision:
    decision_id: str
    allowed: bool
    action: str
    target_nf: str
    target: dict[str, str]
    duration: int | None
    reason: str
    confidence: float
    rejection_reason: str | None = None


class PolicyEngine:
    """Validate model-driven actions against a small deterministic allow-list."""

    def __init__(
        self,
        minimum_confidence: float = 0.8,
        actions: dict[str, dict[str, Any]] | None = None,
    ):
        self.minimum_confidence = minimum_confidence
        self.allowed_nfs = {"AMF", "SMF", "PCF"}
        self.actions: dict[str, dict[str, Any]] = actions or {
            "rate_limit": {"enabled": True, "max_duration": 60},
            "isolate_test_ue": {"enabled": True, "max_duration": 60},
            "terminate_test_session": {"enabled": False, "max_duration": 0},
            "change_test_policy": {"enabled": True, "max_duration": 300},
            "alert_operator": {"enabled": True, "max_duration": 0},
        }

    @classmethod
    def from_yaml(cls, path: str | Path) -> "PolicyEngine":
        with Path(path).open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        return cls(
            minimum_confidence=float(config.get("minimum_confidence", 0.8)),
            actions=config.get("actions"),
        )

    def evaluate(
        self,
        *,
        decision_id: str,
        target_nf: str,
        target: dict[str, str],
        action: str,
        duration: int | None,
        reason: str,
        confidence: float,
    ) -> PolicyDecision:
        rejection_reason = self._validate(
            target_nf, target, action, duration, confidence
        )
        return PolicyDecision(
            decision_id=decision_id,
            allowed=rejection_reason is None,
            action=action,
            target_nf=target_nf,
            target=target,
            duration=duration,
            reason=reason,
            confidence=confidence,
            rejection_reason=rejection_reason,
        )

    def _validate(
        self,
        target_nf: str,
        target: dict[str, str],
        action: str,
        duration: int | None,
        confidence: float,
    ) -> str | None:
        if target_nf not in self.allowed_nfs:
            return "unsupported target NF"
        if not target or any(not key or not value for key, value in target.items()):
            return "target must contain non-empty identifiers"
        if action not in self.actions:
            return "unsupported action"
        action_config = self.actions[action]
        if not action_config["enabled"]:
            return "action is disabled by policy"
        if confidence < self.minimum_confidence:
            return "confidence is below policy threshold"
        max_duration = int(action_config["max_duration"])
        if duration is not None and duration < 0:
            return "duration must not be negative"
        if duration is not None and duration > max_duration:
            return "duration exceeds policy maximum"
        return None