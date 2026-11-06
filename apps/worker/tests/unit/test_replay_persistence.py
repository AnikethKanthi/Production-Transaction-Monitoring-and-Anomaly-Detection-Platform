from unittest.mock import Mock

import pytest
from confluent_kafka import KafkaError, KafkaException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from test_transaction_consumer import event_payload, message

from worker.consumers.transaction_consumer import TransactionConsumer
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
from worker.processors.transaction_processor import TransactionProcessor


def test_database_commit_then_kafka_commit_failure_replay_creates_no_duplicates():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    model = Mock()
    model.decision_function.return_value = [-0.4]
    processor = TransactionProcessor(
        factory,
        anomaly_processor=AnomalyProcessor(model, "fixture.v1"),
        alert_processor=AlertProcessor(AlertPolicy("fixture.v1", 0.2)),
    )
    client = Mock()
    client.commit.side_effect = [KafkaException(KafkaError(KafkaError._TRANSPORT)), None, None]
    consumer = TransactionConsumer(client, processor.process, Mock())
    candidate = message(event_payload())
    with pytest.raises(KafkaException):
        consumer._handle(candidate)
    consumer._handle(candidate)
    consumer._handle(candidate)
    with factory() as session:
        for model in (
            TransactionRecord,
            ProcessedEventRecord,
            InferenceFeatureRecord,
            AnomalyRecord,
            AlertRecord,
            AlertAuditRecord,
        ):
            assert session.scalar(select(func.count()).select_from(model)) == 1
    engine.dispose()
