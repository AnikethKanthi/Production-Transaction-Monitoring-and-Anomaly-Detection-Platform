from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal

from redis import Redis
from redis.exceptions import RedisError

from app.db.repositories.metrics import MetricsRepository
from app.schemas.metrics import MetricsResponse, MetricSummary

logger = logging.getLogger(__name__)


class MetricsCache:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def get(self, key: str) -> dict | None:
        try:
            value = self.redis.get(key)
            return json.loads(value) if value is not None else None
        except (RedisError, ValueError, TypeError):
            logger.warning("Metrics cache read failed", exc_info=True)
            return None

    def set(self, key: str, value: dict) -> None:
        try:
            self.redis.setex(key, self.ttl_seconds, json.dumps(value, separators=(",", ":")))
        except RedisError:
            logger.warning("Metrics cache write failed", exc_info=True)


class MetricsService:
    def __init__(self, repository: MetricsRepository, cache: MetricsCache) -> None:
        self.repository = repository
        self.cache = cache

    def dashboard(
        self, start: datetime, end: datetime, interval: str, currency: str | None
    ) -> MetricsResponse:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must include timezone offsets")
        if start >= end:
            raise ValueError("start must be before end")
        key = self._cache_key(start, end, interval, currency)
        if cached := self.cache.get(key):
            return MetricsResponse.model_validate(cached | {"source": "cache"})
        raw = self.repository.aggregate(start, end, interval, currency)
        response = MetricsResponse(
            start=start,
            end=end,
            interval=interval,
            currency=currency,
            source="database",
            overall=self._summary(raw["overall"]),
            by_country=[self._summary(row) for row in raw["by_country"]],
            by_payment_method=[self._summary(row) for row in raw["by_payment_method"]],
            time_series=[self._summary(row) for row in raw["time_series"]],
        )
        self.cache.set(key, response.model_dump(mode="json"))
        return response

    @staticmethod
    def _summary(row: dict) -> MetricSummary:
        count = int(row["transaction_count"] or 0)
        divisor = count or 1
        label = row.get("label", "all")
        if isinstance(label, datetime):
            label = label.isoformat()
        return MetricSummary(
            label=str(label),
            transaction_count=count,
            transaction_amount=float(Decimal(row["transaction_amount"] or 0)),
            average_transaction_amount=float(Decimal(row["average_transaction_amount"] or 0)),
            success_rate=round(float(row["successes"] or 0) / divisor, 6),
            decline_rate=round(float(row["declines"] or 0) / divisor, 6),
            refund_rate=round(float(row["refunds"] or 0) / divisor, 6),
            anomaly_rate=round(float(row["anomalies"] or 0) / divisor, 6),
            average_processing_latency_ms=round(
                float(row["average_processing_latency_seconds"] or 0) * 1000, 6
            ),
        )

    @staticmethod
    def _cache_key(start: datetime, end: datetime, interval: str, currency: str | None) -> str:
        return f"metrics:v1:{start.isoformat()}:{end.isoformat()}:{interval}:{currency or 'all'}"
