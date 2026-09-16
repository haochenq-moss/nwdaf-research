from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class ResponseVerifier:
    """Compare observed before/after values without inventing unavailable metrics."""

    def verify(
        self,
        *,
        before: dict[str, float],
        after: dict[str, float] | None,
        anomaly_score_before: float,
        anomaly_score_after: float | None,
    ) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc).isoformat()
        if after is None:
            return {
                "status": "unavailable",
                "checked_at": checked_at,
                "available_metrics": {},
                "unavailable_metrics": [
                    "anomaly_score_change",
                    "service_latency_change",
                    "throughput_change",
                    "packet_loss_change",
                ],
            }

        metric_names = {
            "service_latency": "service_latency_change",
            "throughput": "throughput_change",
            "packet_loss": "packet_loss_change",
        }
        available_metrics: dict[str, float] = {}
        unavailable_metrics: list[str] = []
        for source_name, result_name in metric_names.items():
            if source_name in before and source_name in after:
                available_metrics[result_name] = float(after[source_name]) - float(
                    before[source_name]
                )
            else:
                unavailable_metrics.append(result_name)

        if anomaly_score_after is not None:
            available_metrics["anomaly_score_change"] = float(anomaly_score_after) - float(
                anomaly_score_before
            )
        else:
            unavailable_metrics.append("anomaly_score_change")

        return {
            "status": "measured" if available_metrics else "unavailable",
            "checked_at": checked_at,
            "available_metrics": available_metrics,
            "unavailable_metrics": unavailable_metrics,
        }