from datetime import UTC, datetime, timedelta

from redis import Redis
from redis.exceptions import RedisError

from app.schemas.metrics import MetricSummary, RollingMetricsResponse

PREFIX = "metrics:rolling:v1"


class RollingMetricsService:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    def dashboard(self, window_minutes: int, now: datetime | None = None) -> RollingMetricsResponse:
        current = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
        keys = [
            f"{PREFIX}:{(current - timedelta(minutes=offset)).strftime('%Y%m%d%H%M')}"
            for offset in range(window_minutes)
        ]
        try:
            pipeline = self.redis.pipeline(transaction=False)
            for key in keys:
                pipeline.hgetall(key)
            buckets = pipeline.execute()
        except RedisError:
            buckets = []
        total: dict[str, float] = {}
        countries: dict[str, dict[str, float]] = {}
        payment_methods: dict[str, dict[str, float]] = {}
        for bucket in buckets:
            for field, raw_value in bucket.items():
                value = float(raw_value)
                if field.startswith("country:"):
                    _, label, metric = field.split(":", 2)
                    countries.setdefault(label, {})[metric] = (
                        countries.setdefault(label, {}).get(metric, 0) + value
                    )
                elif field.startswith("payment_method:"):
                    _, label, metric = field.split(":", 2)
                    payment_methods.setdefault(label, {})[metric] = (
                        payment_methods.setdefault(label, {}).get(metric, 0) + value
                    )
                else:
                    total[field] = total.get(field, 0) + value
        return RollingMetricsResponse(
            window_minutes=window_minutes,
            overall=self._summary("all", total),
            by_country=[
                self._summary(label, values) for label, values in sorted(countries.items())
            ],
            by_payment_method=[
                self._summary(label, values) for label, values in sorted(payment_methods.items())
            ],
        )

    @staticmethod
    def _summary(label: str, values: dict[str, float]) -> MetricSummary:
        count = int(values.get("count", 0))
        divisor = count or 1
        latency_count = values.get("latency_count", 0) or 1
        amount = values.get("amount", 0)
        return MetricSummary(
            label=label,
            transaction_count=count,
            transaction_amount=round(amount, 6),
            average_transaction_amount=round(amount / divisor, 6),
            success_rate=round(values.get("successes", 0) / divisor, 6),
            decline_rate=round(values.get("declines", 0) / divisor, 6),
            refund_rate=round(values.get("refunds", 0) / divisor, 6),
            anomaly_rate=round(values.get("anomalies", 0) / divisor, 6),
            average_processing_latency_ms=round(
                values.get("latency_seconds", 0) / latency_count * 1000, 6
            ),
        )
