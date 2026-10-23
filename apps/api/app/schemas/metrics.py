from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MetricSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    transaction_count: int
    transaction_amount: float
    average_transaction_amount: float
    success_rate: float
    decline_rate: float
    refund_rate: float
    anomaly_rate: float
    average_processing_latency_ms: float


class MetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    interval: str
    currency: str | None
    source: str
    overall: MetricSummary
    by_country: list[MetricSummary]
    by_payment_method: list[MetricSummary]
    time_series: list[MetricSummary]


class MetricsQuery(BaseModel):
    start: datetime
    end: datetime
    interval: str = Field(default="hour", pattern="^(hour|day)$")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


class RollingMetricsResponse(BaseModel):
    window_minutes: int
    source: str = "redis"
    overall: MetricSummary
    by_country: list[MetricSummary]
    by_payment_method: list[MetricSummary]
