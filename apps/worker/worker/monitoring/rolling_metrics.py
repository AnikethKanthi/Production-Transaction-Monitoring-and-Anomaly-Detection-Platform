import logging
from datetime import UTC

from redis import Redis
from redis.exceptions import RedisError

from worker.events.transaction import TransactionData
from worker.processors.anomaly_processor import ScoreResult

logger = logging.getLogger(__name__)
PREFIX = "metrics:rolling:v1"


class RollingMetricsCounter:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def record(self, transaction: TransactionData, score: ScoreResult) -> None:
        minute = transaction.occurred_at.astimezone(UTC).strftime("%Y%m%d%H%M")
        key = f"{PREFIX}:{minute}"
        payment_method = transaction.payment_method or "unknown"
        flags = {
            "successes": int(transaction.status == "completed"),
            "declines": int(transaction.status == "failed"),
            "refunds": int(transaction.status == "refunded"),
            "anomalies": int(score.status == "scored" and score.score > 0),
        }
        values = {
            "count": 1,
            "amount": float(transaction.amount),
            "latency_count": 1,
            "latency_seconds": score.latency_seconds,
            **flags,
        }
        try:
            pipeline = self.redis.pipeline(transaction=True)
            for metric, value in values.items():
                pipeline.hincrbyfloat(key, metric, value)
                pipeline.hincrbyfloat(key, f"country:{transaction.country}:{metric}", value)
                pipeline.hincrbyfloat(key, f"payment_method:{payment_method}:{metric}", value)
            pipeline.expire(key, self.ttl_seconds)
            pipeline.execute()
        except RedisError:
            logger.warning("Rolling metrics update failed key=%s", key, exc_info=True)
