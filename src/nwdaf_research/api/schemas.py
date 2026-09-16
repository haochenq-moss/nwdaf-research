from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nf: str = Field(min_length=1)
    supi: str | None = Field(default=None, min_length=1)


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime


class AnalyticsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    analytics_id: str = Field(alias="analyticsId", min_length=1)
    target: AnalyticsTarget
    time_window: TimeWindow = Field(alias="timeWindow")
    features: dict[str, float]


class AnalyticsResult(BaseModel):
    anomaly_score: float = Field(alias="anomalyScore", ge=0.0, le=1.0)
    classification: str
    confidence: float = Field(ge=0.0, le=1.0)
    severity: str

    model_config = ConfigDict(populate_by_name=True)


class ModelInfo(BaseModel):
    name: str
    version: str
    feature_schema: str = Field(alias="featureSchema")

    model_config = ConfigDict(populate_by_name=True)


class AnalyticsResponse(BaseModel):
    analytics_id: str = Field(alias="analyticsId")
    timestamp: datetime
    result: AnalyticsResult
    model: ModelInfo

    model_config = ConfigDict(populate_by_name=True)


class SubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    notification_uri: str = Field(alias="notificationUri", min_length=1)
    analytics_id: str = Field(alias="analyticsId", min_length=1)
    target: dict[str, Any]
    reporting_interval: int = Field(alias="reportingInterval", gt=0, le=86400)


class SubscriptionResponse(SubscriptionRequest):
    subscription_id: str = Field(alias="subscriptionId")


class AnalyticsNotification(BaseModel):
    subscription_id: str = Field(alias="subscriptionId")
    notification_uri: str = Field(alias="notificationUri")
    analytics_id: str = Field(alias="analyticsId")
    timestamp: datetime
    result: AnalyticsResult
    delivery_status: str = Field(default="not_requested", alias="deliveryStatus")
    delivery_error: str | None = Field(default=None, alias="deliveryError")

    model_config = ConfigDict(populate_by_name=True)


class MitigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    decision_id: str = Field(alias="decisionId", min_length=1)
    target_nf: str = Field(alias="targetNF", min_length=1)
    target: dict[str, str]
    action: str = Field(min_length=1)
    duration: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class MitigationResponse(BaseModel):
    decision_id: str = Field(alias="decisionId")
    status: str
    action: str
    target_nf: str = Field(alias="targetNF")
    rejection_reason: str | None = Field(default=None, alias="rejectionReason")

    model_config = ConfigDict(populate_by_name=True)
