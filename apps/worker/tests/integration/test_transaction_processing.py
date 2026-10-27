from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from worker.consumers.transaction_consumer import TransactionConsumer
from worker.events.transaction import TransactionData, TransactionEvent, serialize_transaction_event
from worker.persistence.models import (
    AlertRecord,
    AnomalyRecord,
    InferenceFeatureRecord,
    ProcessedEventRecord,
    TransactionRecord,
)
from worker.processors.alert_processor import AlertPolicy, AlertProcessor
from worker.processors.anomaly_processor import AnomalyProcessor
from worker.processors.transaction_processor import ProcessingResult, TransactionProcessor

pytestmark = pytest.mark.integration


class AlertingModel:
    def decision_function(self, values):
        return [-0.4]


def test_qualifying_event_creates_one_alert_on_postgres(session_factory) -> None:
    transaction_event = event()
    processor = TransactionProcessor(
        session_factory,
        anomaly_processor=AnomalyProcessor(AlertingModel(), "fixture.v1"),
        alert_processor=AlertProcessor(AlertPolicy("fixture.v1", 0.2)),
    )
    assert processor.process(transaction_event) == ProcessingResult.processed
    assert processor.process(transaction_event) == ProcessingResult.duplicate
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AlertRecord)) == 1
        alert = session.scalar(select(AlertRecord))
        anomaly = session.scalar(select(AnomalyRecord))
        assert alert.anomaly_id == anomaly.id
        assert alert.severity == "critical"
        assert "threshold" in alert.evidence["reasons"][0]


def event() -> TransactionEvent:
    now = datetime.now(UTC)
    return TransactionEvent(
        produced_at=now,
        data=TransactionData(
            transaction_id=uuid4(),
            account_id="acct-integration",
            amount=Decimal("25.00"),
            currency="USD",
            country="US",
            status="completed",
            occurred_at=now,
        ),
    )


def test_replay_is_idempotent(session_factory: sessionmaker[Session]) -> None:
    transaction_event = event()
    processor = TransactionProcessor(session_factory)

    assert processor.process(transaction_event) == ProcessingResult.processed
    assert processor.process(transaction_event) == ProcessingResult.duplicate

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TransactionRecord)) == 1
        assert session.scalar(select(func.count()).select_from(ProcessedEventRecord)) == 1
        assert session.scalar(select(func.count()).select_from(InferenceFeatureRecord)) == 1
        assert session.scalar(select(func.count()).select_from(AnomalyRecord)) == 1
        stored = session.scalar(select(InferenceFeatureRecord))
        assert stored is not None
        assert stored.feature_definition_version == "transaction_features.v1"
        assert stored.features["transaction_amount"] == 25.0
        anomaly = session.scalar(select(AnomalyRecord))
        assert anomaly is not None
        assert anomaly.model_version == "fallback.v1"
        assert anomaly.scoring_status == "fallback"
        assert anomaly.score == 0.0


def test_transient_failure_retries_then_persists(session_factory: sessionmaker[Session]) -> None:
    transaction_event = event()
    persistent_processor = TransactionProcessor(session_factory)
    attempts = 0

    def flaky_processor(candidate: TransactionEvent) -> object:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary database outage")
        return persistent_processor.process(candidate)

    message = Mock()
    message.value.return_value = serialize_transaction_event(transaction_event)
    message.key.return_value = str(transaction_event.data.transaction_id).encode()
    message.topic.return_value = "transactions.v1"
    message.partition.return_value = 1
    message.offset.return_value = 7
    consumer = Mock()
    dead_letter = Mock()

    TransactionConsumer(
        consumer,
        flaky_processor,
        dead_letter,
        max_processing_attempts=3,
        retry_backoff_seconds=0,
    )._handle(message)

    assert attempts == 3
    dead_letter.assert_not_called()
    consumer.commit.assert_called_once_with(message=message, asynchronous=False)
    with session_factory() as session:
        assert session.get(ProcessedEventRecord, transaction_event.event_id) is not None
