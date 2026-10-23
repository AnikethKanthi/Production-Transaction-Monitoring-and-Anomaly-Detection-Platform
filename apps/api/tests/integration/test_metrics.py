from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from app.db.repositories.metrics import MetricsRepository
from app.models import Anomaly, Transaction
from app.services.metrics_service import MetricsService

pytestmark = pytest.mark.integration


class NoCache:
    def get(self, key: str) -> None:
        return None

    def set(self, key: str, value: dict) -> None:
        return None


def test_metrics_match_known_database_fixtures(migrated_connection: Connection) -> None:
    start = datetime(2026, 10, 23, 10, tzinfo=UTC)
    statuses = ("completed", "completed", "failed", "refunded")
    amounts = ("10.00", "20.00", "30.00", "40.00")
    with Session(migrated_connection) as session:
        transactions = []
        for index, (status, amount) in enumerate(zip(statuses, amounts)):
            transaction = Transaction(
                id=uuid4(),
                account_id=f"acct-{index}",
                amount=Decimal(amount),
                currency="USD",
                country="US" if index < 3 else "CA",
                status=status,
                occurred_at=start.replace(hour=10 + index),
                payment_method="card" if index < 2 else "bank",
            )
            transactions.append(transaction)
            session.add(transaction)
        session.flush()
        for index, score in enumerate((0.2, -0.1)):
            session.add(
                Anomaly(
                    id=uuid4(),
                    transaction_id=transactions[index].id,
                    score=score,
                    model_version="fixture.v1",
                    scoring_status="scored",
                    inference_latency_seconds=0.01 * (index + 1),
                )
            )
        session.commit()

        response = MetricsService(MetricsRepository(session), NoCache()).dashboard(
            start, start.replace(hour=14), "hour", "USD"
        )

    assert response.overall.transaction_count == 4
    assert response.overall.transaction_amount == 100.0
    assert response.overall.average_transaction_amount == 25.0
    assert response.overall.success_rate == 0.5
    assert response.overall.decline_rate == 0.25
    assert response.overall.refund_rate == 0.25
    assert response.overall.anomaly_rate == 0.25
    assert response.overall.average_processing_latency_ms == 15.0
    assert [(item.label, item.transaction_count) for item in response.by_country] == [
        ("CA", 1),
        ("US", 3),
    ]
    assert len(response.time_series) == 4
