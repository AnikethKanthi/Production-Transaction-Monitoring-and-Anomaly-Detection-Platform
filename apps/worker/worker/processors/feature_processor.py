from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from worker.events.transaction import TransactionEvent
from worker.features.transaction_v1 import (
    FEATURE_DEFINITION_VERSION,
    HistoricalTransaction,
    TransactionFeatureVector,
    transform_transaction_features,
)
from worker.persistence.models import InferenceFeatureRecord, TransactionRecord


class FeatureProcessor:
    def build(self, session: Session, event: TransactionEvent) -> TransactionFeatureVector:
        rows = session.scalars(
            select(TransactionRecord)
            .where(
                TransactionRecord.account_id == event.data.account_id,
                TransactionRecord.occurred_at <= event.data.occurred_at,
            )
            .order_by(TransactionRecord.occurred_at, TransactionRecord.id)
        )
        history = [
            HistoricalTransaction(
                transaction_id=row.id,
                amount=row.amount,
                currency=row.currency,
                country=row.country,
                status=row.status,
                occurred_at=row.occurred_at,
                device_id=row.device_id,
                ip_address=row.ip_address,
                payment_method=row.payment_method,
                order_amount=row.order_amount,
            )
            for row in rows
        ]
        return transform_transaction_features(event.data, history)

    def store(
        self, session: Session, event: TransactionEvent, features: TransactionFeatureVector
    ) -> InferenceFeatureRecord:
        record = InferenceFeatureRecord(
            id=uuid4(),
            transaction_id=event.data.transaction_id,
            event_id=event.event_id,
            feature_definition_version=FEATURE_DEFINITION_VERSION,
            features=features.model_dump(mode="json"),
        )
        session.add(record)
        return record
