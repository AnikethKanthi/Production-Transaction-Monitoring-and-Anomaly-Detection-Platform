from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import numpy as np
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from worker.events.transaction import TransactionData, TransactionEvent
from worker.persistence.models import AnomalyRecord, Base, ProcessedEventRecord
from worker.processors.anomaly_processor import AnomalyProcessor
from worker.processors.transaction_processor import ProcessingResult, TransactionProcessor


class FixedModel:
    def decision_function(self, values: np.ndarray) -> np.ndarray:
        return np.asarray([-0.375])


def test_processed_transactions_store_model_and_fallback_scores() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    transaction = TransactionEvent(
        produced_at=now,
        data=TransactionData(
            transaction_id=uuid4(),
            account_id="acct-score-test",
            amount=Decimal("250.00"),
            currency="USD",
            country="US",
            status="completed",
            occurred_at=now,
        ),
    )
    processor = TransactionProcessor(
        factory, anomaly_processor=AnomalyProcessor(FixedModel(), "test-model.v1")
    )

    assert processor.process(transaction) == ProcessingResult.processed
    fallback_transaction = TransactionEvent(
        produced_at=now,
        data=transaction.data.model_copy(
            update={"transaction_id": uuid4(), "account_id": "acct-fallback-test"}
        ),
    )
    assert TransactionProcessor(factory).process(fallback_transaction) == ProcessingResult.processed

    with Session(engine) as session:
        anomaly = session.scalar(
            select(AnomalyRecord).where(
                AnomalyRecord.transaction_id == transaction.data.transaction_id
            )
        )
        assert anomaly is not None
        assert anomaly.transaction_id == transaction.data.transaction_id
        assert anomaly.score == 0.375
        assert anomaly.model_version == "test-model.v1"
        assert anomaly.scoring_status == "scored"
        assert anomaly.inference_latency_seconds >= 0
        assert session.get(ProcessedEventRecord, transaction.event_id) is not None
        fallback = session.scalar(
            select(AnomalyRecord).where(
                AnomalyRecord.transaction_id == fallback_transaction.data.transaction_id
            )
        )
        assert fallback is not None
        assert fallback.score == 0.0
        assert fallback.model_version == "fallback.v1"
        assert fallback.scoring_status == "fallback"
        assert session.get(ProcessedEventRecord, fallback_transaction.event_id) is not None
    engine.dispose()
