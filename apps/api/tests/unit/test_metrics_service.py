from datetime import UTC, datetime

from app.services.metrics_service import MetricsCache, MetricsService


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.expirations[key] = ttl


class FixtureRepository:
    calls = 0

    def aggregate(self, start, end, interval, currency) -> dict:
        self.calls += 1
        summary = {
            "label": "all",
            "transaction_count": 4,
            "transaction_amount": 100,
            "average_transaction_amount": 25,
            "successes": 2,
            "declines": 1,
            "refunds": 1,
            "anomalies": 1,
            "average_processing_latency_seconds": 0.012,
        }
        return {
            "overall": summary,
            "by_country": [summary | {"label": "US"}],
            "by_payment_method": [summary | {"label": "card"}],
            "time_series": [summary | {"label": start}],
        }


def test_database_metrics_are_cached_with_expiration() -> None:
    redis = FakeRedis()
    repository = FixtureRepository()
    service = MetricsService(repository, MetricsCache(redis, ttl_seconds=45))
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 2, tzinfo=UTC)

    database = service.dashboard(start, end, "hour", "USD")
    cached = service.dashboard(start, end, "hour", "USD")

    assert database.source == "database"
    assert cached.source == "cache"
    assert repository.calls == 1
    assert set(redis.expirations.values()) == {45}
    assert database.overall.model_dump() == {
        "label": "all",
        "transaction_count": 4,
        "transaction_amount": 100.0,
        "average_transaction_amount": 25.0,
        "success_rate": 0.5,
        "decline_rate": 0.25,
        "refund_rate": 0.25,
        "anomaly_rate": 0.25,
        "average_processing_latency_ms": 12.0,
    }
