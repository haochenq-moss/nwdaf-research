from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class OperationalReport:
    report_id: str
    lifecycle: str
    analytics_id: str | None
    severity: str | None
    confidence: float | None
    action_status: str
    evidence: dict[str, Any]
    created_at: str


class VFLReporter:
    """Operational reporting adapter for OAM/OSS-style consumers."""

    def create(
        self,
        *,
        report_id: str,
        lifecycle: str,
        analytics_id: str | None = None,
        severity: str | None = None,
        confidence: float | None = None,
        action_status: str = "not_requested",
        evidence: dict[str, Any] | None = None,
    ) -> OperationalReport:
        return OperationalReport(
            report_id=report_id,
            lifecycle=lifecycle,
            analytics_id=analytics_id,
            severity=severity,
            confidence=confidence,
            action_status=action_status,
            evidence=evidence or {},
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def as_payload(self, report: OperationalReport) -> dict[str, Any]:
        return {
            "reportId": report.report_id,
            "lifecycle": report.lifecycle,
            "analyticsId": report.analytics_id,
            "severity": report.severity,
            "confidence": report.confidence,
            "actionStatus": report.action_status,
            "evidence": report.evidence,
            "createdAt": report.created_at,
        }