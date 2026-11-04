"""Bounded-label, database-authoritative five-minute operational snapshot."""

from datetime import UTC, datetime, timedelta

from prometheus_client import CollectorRegistry, Gauge, generate_latest
from sqlalchemy import DateTime, bindparam, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_engine


def snapshot(engine=None, now=None) -> bytes:
    registry = CollectorRegistry()
    health = Gauge("platform_database_up", "Database snapshot query succeeded.", registry=registry)
    try:
        with (engine or get_engine()).connect() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET LOCAL statement_timeout = '2000ms'"))
            cutoff = (now or datetime.now(UTC)) - timedelta(minutes=5)
            params = {"cutoff": cutoff}
            transactions = connection.execute(
                text(
                    "SELECT status, count(*) FROM transactions "
                    "WHERE created_at >= :cutoff GROUP BY status"
                ).bindparams(bindparam("cutoff", type_=DateTime(timezone=True))),
                params,
            ).all()
            anomalies = connection.execute(
                text(
                    "SELECT count(*), count(CASE WHEN score > 0 THEN 1 END) "
                    "FROM anomalies WHERE scoring_status = 'scored' AND created_at >= :cutoff"
                ).bindparams(bindparam("cutoff", type_=DateTime(timezone=True))),
                params,
            ).one()
            alerts = connection.execute(
                text(
                    "SELECT severity, count(*) FROM alerts "
                    "WHERE created_at >= :cutoff GROUP BY severity"
                ).bindparams(bindparam("cutoff", type_=DateTime(timezone=True))),
                params,
            ).all()
        health.set(1)
        counts = dict(transactions)
        metric = Gauge(
            "platform_transactions_5m",
            "Transactions ingested in the last five minutes.",
            ["status"],
            registry=registry,
        )
        for status in ("pending", "completed", "failed", "refunded"):
            metric.labels(status).set(counts.get(status, 0))
        Gauge("platform_scored_5m", "Model-scored records in five minutes.", registry=registry).set(
            anomalies[0]
        )
        Gauge(
            "platform_anomalies_5m", "Positive model scores in five minutes.", registry=registry
        ).set(anomalies[1])
        metric = Gauge(
            "platform_alerts_5m",
            "Alerts created in five minutes, all workflow states.",
            ["severity"],
            registry=registry,
        )
        counts = dict(alerts)
        for severity in ("low", "medium", "high", "critical"):
            metric.labels(severity).set(counts.get(severity, 0))
    except SQLAlchemyError:
        # Omit business values on failure: missing data must never look like zero traffic.
        health.set(0)
    return generate_latest(registry)
