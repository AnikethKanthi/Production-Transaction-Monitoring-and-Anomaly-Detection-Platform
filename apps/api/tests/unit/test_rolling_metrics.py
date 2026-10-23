from datetime import UTC, datetime

from app.services.rolling_metrics import RollingMetricsService


class Pipeline:
    def __init__(self, buckets: dict[str, dict[str, str]]) -> None:
        self.buckets = buckets
        self.keys: list[str] = []

    def hgetall(self, key: str):
        self.keys.append(key)
        return self

    def execute(self) -> list[dict[str, str]]:
        return [self.buckets.get(key, {}) for key in self.keys]


class FakeRedis:
    def __init__(self, buckets: dict[str, dict[str, str]]) -> None:
        self.buckets = buckets

    def pipeline(self, transaction: bool) -> Pipeline:
        assert transaction is False
        return Pipeline(self.buckets)


def test_rolling_dashboard_combines_minute_buckets() -> None:
    buckets = {
        "metrics:rolling:v1:202610231200": {
            "count": "1",
            "amount": "10",
            "successes": "1",
            "latency_count": "1",
            "latency_seconds": "0.01",
            "country:US:count": "1",
            "country:US:amount": "10",
            "payment_method:card:count": "1",
            "payment_method:card:amount": "10",
        },
        "metrics:rolling:v1:202610231159": {
            "count": "1",
            "amount": "30",
            "declines": "1",
            "anomalies": "1",
            "latency_count": "1",
            "latency_seconds": "0.03",
            "country:GB:count": "1",
            "country:GB:amount": "30",
            "payment_method:bank:count": "1",
            "payment_method:bank:amount": "30",
        },
    }
    response = RollingMetricsService(FakeRedis(buckets)).dashboard(
        2, datetime(2026, 10, 23, 12, tzinfo=UTC)
    )
    assert response.overall.transaction_count == 2
    assert response.overall.transaction_amount == 40
    assert response.overall.average_transaction_amount == 20
    assert response.overall.success_rate == 0.5
    assert response.overall.decline_rate == 0.5
    assert response.overall.anomaly_rate == 0.5
    assert response.overall.average_processing_latency_ms == 20
    assert [item.label for item in response.by_country] == ["GB", "US"]
