from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.orm import sessionmaker

from worker.events.transaction import TransactionData, TransactionEvent
from worker.features.transaction_v1 import TransactionFeatureVector
from worker.persistence.models import (
    AlertAuditRecord,
    AlertRecord,
    AnomalyRecord,
    Base,
    InferenceFeatureRecord,
    ProcessedEventRecord,
    TransactionRecord,
)
from worker.processors.alert_processor import AlertPolicy, AlertProcessor
from worker.processors.anomaly_processor import AnomalyProcessor
from worker.processors.transaction_processor import ProcessingResult, TransactionProcessor


class SuspiciousModel:
    def decision_function(self, values):
        return np.asarray([-0.4])


@pytest.fixture
def factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @sqlalchemy_event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def transaction_event():
    now = datetime.now(UTC)
    return TransactionEvent(
        produced_at=now,
        data=TransactionData(
            transaction_id=uuid4(),
            account_id="suspicious-account",
            amount=Decimal("5000"),
            currency="USD",
            country="US",
            status="completed",
            occurred_at=now,
        ),
    )


def test_alert_is_atomic_and_replay_or_repeat_policy_does_not_duplicate(factory) -> None:
    alerts = AlertProcessor(AlertPolicy("test.v1", 0.2))
    anomaly_processor = AnomalyProcessor(SuspiciousModel(), "test.v1")
    processor = TransactionProcessor(
        factory, anomaly_processor=anomaly_processor, alert_processor=alerts
    )
    event = transaction_event()
    assert processor.process(event) == ProcessingResult.processed
    assert processor.process(event) == ProcessingResult.duplicate
    with factory.begin() as session:
        alert = session.scalar(select(AlertRecord))
        anomaly = session.scalar(select(AnomalyRecord))
        assert alert is not None and anomaly is not None
        assert alert.anomaly_id == anomaly.id
        assert alert.model_version == anomaly.model_version == "test.v1"
        assert alert.severity == "critical"
        assert alert.evidence["score"] == anomaly.score
        assert alert.event_id == event.event_id
        feature_record = session.scalar(select(InferenceFeatureRecord))
        assert feature_record is not None
        stored_features = TransactionFeatureVector.model_validate(feature_record.features)
        # Simulate an independently redelivered alert decision with a new event ID.
        redelivered = event.model_copy(update={"event_id": uuid4()})
        assert not alerts.store(
            session,
            redelivered,
            anomaly.id,
            anomaly_processor.score(stored_features),
            stored_features,
        )
        assert session.scalar(select(func.count()).select_from(AlertRecord)) == 1
        history = list(session.scalars(select(AlertAuditRecord)))
        assert len(history) == 1
        assert history[0].action == "create"
        assert history[0].version == 1
        assert history[0].after == {"status": "open", "assignee": None, "version": 1}
        assert session.scalar(select(func.count()).select_from(ProcessedEventRecord)) == 1


class FailingAlerts:
    def store(self, *args):
        raise RuntimeError("alert storage failed")


def test_alert_storage_failure_rolls_back_entire_event(factory) -> None:
    processor = TransactionProcessor(
        factory,
        anomaly_processor=AnomalyProcessor(SuspiciousModel(), "test.v1"),
        alert_processor=FailingAlerts(),
    )
    with pytest.raises(RuntimeError, match="alert storage failed"):
        processor.process(transaction_event())
    with factory() as session:
        for table in (
            TransactionRecord,
            AnomalyRecord,
            AlertRecord,
            AlertAuditRecord,
            ProcessedEventRecord,
        ):
            assert session.scalar(select(func.count()).select_from(table)) == 0


def test_fallback_transaction_persists_without_alert(factory) -> None:
    processor = TransactionProcessor(
        factory, alert_processor=AlertProcessor(AlertPolicy("test.v1", 0.2))
    )
    assert processor.process(transaction_event()) == ProcessingResult.processed
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AlertRecord)) == 0
        assert session.scalar(select(func.count()).select_from(AnomalyRecord)) == 1
