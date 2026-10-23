from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from worker.events.transaction import TransactionData
from worker.monitoring.rolling_metrics import RollingMetricsCounter
from worker.processors.anomaly_processor import ScoreResult


class Pipeline:
    def __init__(self) -> None:
        self.increments: list[tuple[str, str, float]] = []
        self.expiration: tuple[str, int] | None = None

    def hincrbyfloat(self, key: str, field: str, value: float):
        self.increments.append((key, field, value))
        return self

    def expire(self, key: str, ttl: int):
        self.expiration = (key, ttl)
        return self

    def execute(self) -> list:
        return []


class FakeRedis:
    def __init__(self) -> None:
        self.created = Pipeline()

    def pipeline(self, transaction: bool) -> Pipeline:
        assert transaction is True
        return self.created


def test_rolling_counter_records_breakdowns_and_expiration() -> None:
    redis = FakeRedis()
    counter = RollingMetricsCounter(redis, ttl_seconds=300)
    transaction = TransactionData(
        transaction_id=uuid4(),
        account_id="acct-1",
        amount=Decimal("125.50"),
        currency="USD",
        country="US",
        status="refunded",
        occurred_at=datetime(2026, 10, 23, 14, 31, tzinfo=UTC),
        payment_method="card",
    )
    counter.record(transaction, ScoreResult(0.4, "model.v1", "scored", None, 0.02))

    key = "metrics:rolling:v1:202610231431"
    assert redis.created.expiration == (key, 300)
    assert (key, "count", 1) in redis.created.increments
    assert (key, "refunds", 1) in redis.created.increments
    assert (key, "anomalies", 1) in redis.created.increments
    assert (key, "country:US:amount", 125.5) in redis.created.increments
    assert (key, "payment_method:card:count", 1) in redis.created.increments
