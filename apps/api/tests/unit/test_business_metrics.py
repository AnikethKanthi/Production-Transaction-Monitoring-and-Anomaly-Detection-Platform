import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.core.business_metrics import snapshot


def samples(payload):
    return {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in text_string_to_metric_families(payload.decode())
        for sample in family.samples
    }


def test_snapshot_counts_persisted_records_and_excludes_old_data():
    engine = create_engine("sqlite://")
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE transactions (status TEXT, created_at TIMESTAMP)"))
        connection.execute(
            text("CREATE TABLE anomalies (score FLOAT, scoring_status TEXT, created_at TIMESTAMP)")
        )
        connection.execute(text("CREATE TABLE alerts (severity TEXT, created_at TIMESTAMP)"))
        for status, timestamp in [
            ("completed", now),
            ("failed", now),
            ("completed", now - timedelta(minutes=6)),
        ]:
            connection.execute(
                text("INSERT INTO transactions VALUES (:s, :t)"),
                {"s": status, "t": timestamp.isoformat(sep=" ")},
            )
        connection.execute(
            text(
                "INSERT INTO anomalies VALUES (0.3, 'scored', :t), "
                "(-0.1, 'scored', :t), (0, 'fallback', :t)"
            ),
            {"t": now.isoformat(sep=" ")},
        )
        connection.execute(
            text("INSERT INTO alerts VALUES ('high', :t)"), {"t": now.isoformat(sep=" ")}
        )
    result = samples(snapshot(engine, now))
    assert result[("platform_database_up", ())] == 1
    assert result[("platform_transactions_5m", (("status", "completed"),))] == 1
    assert result[("platform_transactions_5m", (("status", "failed"),))] == 1
    assert result[("platform_transactions_5m", (("status", "pending"),))] == 0
    assert result[("platform_scored_5m", ())] == 2
    assert result[("platform_anomalies_5m", ())] == 1
    assert result[("platform_alerts_5m", (("severity", "high"),))] == 1
    assert result[("platform_alerts_5m", (("severity", "low"),))] == 0
    engine.dispose()


def test_query_failure_reports_unhealthy_without_false_zero_business_values():
    engine = create_engine("sqlite://")
    assert samples(snapshot(engine)) == {("platform_database_up", ()): 0}
    engine.dispose()


def test_business_scrape_endpoint_excludes_itself_from_request_metrics(monkeypatch):
    from app.core.telemetry import REQUESTS
    from app.main import app

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    monkeypatch.setattr("app.main.snapshot", lambda: snapshot(engine))

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/metrics/business")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert samples(response.content) == {("platform_database_up", ()): 0}
    assert not any(
        sample.labels.get("route") == "/metrics/business"
        for family in REQUESTS.collect()
        for sample in family.samples
    )
    engine.dispose()
