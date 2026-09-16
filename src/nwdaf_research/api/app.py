from __future__ import annotations

import uuid
from datetime import datetime, timezone
import os
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status

from nwdaf_research.adapters.mock_nf import MockNFAdapter
from nwdaf_research.adapters.http_nf import HTTPNFAdapter
from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer
from nwdaf_research.policy.engine import PolicyEngine
from nwdaf_research.security.audit import AuditLogger
from .persistence import APIState

from .schemas import (
    AnalyticsRequest,
    AnalyticsResponse,
    AnalyticsResult,
    ModelInfo,
    AnalyticsNotification,
    MitigationRequest,
    MitigationResponse,
    SubscriptionRequest,
    SubscriptionResponse,
)


def _severity(score: float) -> str:
    if score >= 0.9:
        return "high"
    if score >= 0.7:
        return "medium"
    return "low"


def create_app(
    raw_root: str | Path,
    audit_path: str | Path | None = None,
    policy_config: str | Path | None = None,
    model_artifact: str | Path | None = None,
    response_agent_endpoint: str | None = None,
    response_agent_api_key: str | None = None,
) -> FastAPI:
    analyzer = NWDAFResearchAnalyzer(raw_root, model_artifact=model_artifact)
    default_policy_config = Path(raw_root).resolve().parents[1] / "configs" / "policy.yaml"
    selected_policy_config = Path(policy_config) if policy_config else default_policy_config
    policy = (
        PolicyEngine.from_yaml(selected_policy_config)
        if selected_policy_config.exists()
        else PolicyEngine()
    )
    adapter = (
        HTTPNFAdapter(response_agent_endpoint, response_agent_api_key)
        if response_agent_endpoint and response_agent_api_key
        else MockNFAdapter()
    )
    audit = AuditLogger(audit_path)
    state_path = (
        Path(f"{audit_path}.sqlite3")
        if audit_path
        else Path("/tmp") / f"nwdaf-api-{uuid.uuid4().hex}.sqlite3"
    )
    state = APIState(state_path)
    subscriptions: dict[str, SubscriptionResponse] = {}
    recent_analytics: dict[str, AnalyticsResponse] = {}
    app = FastAPI(
        title="NWDAF-like Security Analytics Prototype",
        version="0.1.0",
        description="Experimental SBA-inspired analytics interface; not 3GPP-compliant NWDAF.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    def require_api_key(request: Request) -> None:
        expected = os.getenv("NWDAF_API_KEY")
        if expected and request.headers.get("X-API-Key") != expected:
            raise HTTPException(status_code=401, detail="invalid or missing API key")

    def audit_request(request: Request, event_type: str, outcome: str, **details: Any) -> None:
        audit.record(
            {
                "event_type": event_type,
                "outcome": outcome,
                "request_id": request.state.request_id,
                "path": request.url.path,
                **details,
            }
        )

    @app.post(
        "/nnwdaf-analyticsinfo/v1/security-analytics",
        response_model=AnalyticsResponse,
    )
    def security_analytics(http_request: Request, request: AnalyticsRequest) -> AnalyticsResponse:
        require_api_key(http_request)
        if request.time_window.end < request.time_window.start:
            raise HTTPException(
                status_code=422,
                detail="timeWindow.end must not precede timeWindow.start",
            )

        scored = analyzer.score_features(request.features)
        score = float(scored["anomaly_probability"])
        response = AnalyticsResponse(
            analyticsId=request.analytics_id,
            timestamp=datetime.now(timezone.utc),
            result=AnalyticsResult(
                anomalyScore=score,
                classification=scored["predicted_label"].lower(),
                confidence=float(scored["confidence"]),
                severity=_severity(score),
            ),
            model=ModelInfo(
                name=scored["model_name"],
                version=scored["model_version"],
                featureSchema=scored["feature_schema"],
            ),
        )
        audit_request(
            http_request,
            "analytics_request",
            "accepted",
            analytics_id=request.analytics_id,
            classification=response.result.classification,
            model_version=response.model.version,
        )
        recent_analytics[request.analytics_id] = response
        return response

    @app.post(
        "/nnwdaf-eventssubscription/v1/subscriptions",
        response_model=SubscriptionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_subscription(
        http_request: Request, request: SubscriptionRequest
    ) -> SubscriptionResponse:
        require_api_key(http_request)
        subscription_id = f"sub-{uuid.uuid4().hex[:12]}"
        subscription = SubscriptionResponse(
            **request.model_dump(), subscriptionId=subscription_id
        )
        subscriptions[subscription_id] = subscription
        state.save_subscription(subscription_id, subscription.model_dump(by_alias=True))
        audit_request(
            http_request,
            "subscription_request",
            "accepted",
            subscription_id=subscription_id,
        )
        return subscription

    @app.get(
        "/nnwdaf-eventssubscription/v1/subscriptions",
        response_model=list[SubscriptionResponse],
    )
    def list_subscriptions(http_request: Request) -> list[SubscriptionResponse]:
        require_api_key(http_request)
        persisted = [SubscriptionResponse(**payload) for _, payload in state.subscriptions()]
        return persisted or list(subscriptions.values())

    @app.post(
        "/nnwdaf-eventssubscription/v1/notifications",
        response_model=list[AnalyticsNotification],
    )
    def generate_notifications(
        http_request: Request, analytics_id: str | None = None, deliver: bool = False
    ) -> list[AnalyticsNotification]:
        require_api_key(http_request)
        notifications: list[AnalyticsNotification] = []
        persisted = state.subscriptions()
        candidates = persisted or [(subscription_id, subscription.model_dump(by_alias=True)) for subscription_id, subscription in subscriptions.items()]
        for subscription_id, payload in candidates:
            subscription = SubscriptionResponse(**payload)
            if analytics_id and subscription.analytics_id != analytics_id:
                continue
            response = recent_analytics.get(subscription.analytics_id)
            if response is None:
                continue
            notification = AnalyticsNotification(
                    subscriptionId=subscription_id,
                    notificationUri=subscription.notification_uri,
                    analyticsId=response.analytics_id,
                    timestamp=response.timestamp,
                    result=response.result,
                )
            if deliver:
                try:
                    request = urllib.request.Request(
                        subscription.notification_uri,
                        data=json.dumps(notification.model_dump(by_alias=True)).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(request, timeout=3) as response:
                        notification.delivery_status = "delivered" if 200 <= response.status < 300 else "failed"
                except (OSError, urllib.error.URLError) as error:
                    notification.delivery_status = "failed"
                    notification.delivery_error = str(error)
            notifications.append(notification)
        audit_request(
            http_request,
            "notification_generation",
            "accepted",
            analytics_id=analytics_id,
            notification_count=len(notifications),
            delivery_requested=deliver,
        )
        return notifications

    @app.post("/security/v1/mitigation", response_model=MitigationResponse)
    def mitigation(
        http_request: Request, request: MitigationRequest
    ) -> MitigationResponse:
        require_api_key(http_request)
        if not state.claim_decision(request.decision_id):
            audit_request(
                http_request,
                "mitigation_request",
                "rejected_replay",
                decision_id=request.decision_id,
            )
            raise HTTPException(status_code=409, detail="decisionId has already been used")
        decision = policy.evaluate(
            decision_id=request.decision_id,
            target_nf=request.target_nf,
            target=request.target,
            action=request.action,
            duration=request.duration,
            reason=request.reason,
            confidence=request.confidence,
        )
        if not decision.allowed:
            audit_request(
                http_request,
                "mitigation_request",
                "rejected_policy",
                decision_id=decision.decision_id,
                rejection_reason=decision.rejection_reason,
            )
            raise HTTPException(
                status_code=422,
                detail=decision.rejection_reason,
            )
        adapter.execute(decision)
        audit_request(
            http_request,
            "mitigation_request",
            "accepted",
            decision_id=decision.decision_id,
            action=decision.action,
            target_nf=decision.target_nf,
        )
        return MitigationResponse(
            decisionId=decision.decision_id,
            status="accepted",
            action=decision.action,
            targetNF=decision.target_nf,
        )

    return app