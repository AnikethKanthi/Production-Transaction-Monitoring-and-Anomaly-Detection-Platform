import logging
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from worker.events.transaction import TransactionEvent
from worker.persistence.models import ProcessedEventRecord, TransactionRecord
from worker.processors.feature_processor import FeatureProcessor

logger = logging.getLogger(__name__)


class ProcessingResult(StrEnum):
    processed = "processed"
    duplicate = "duplicate"


class TransactionProcessor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        feature_processor: FeatureProcessor | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.feature_processor = feature_processor or FeatureProcessor()

    def process(self, event: TransactionEvent) -> ProcessingResult:
        with self.session_factory.begin() as session:
            already_processed = session.scalar(
                select(ProcessedEventRecord.event_id).where(
                    ProcessedEventRecord.event_id == event.event_id
                )
            )
            if already_processed is not None:
                logger.info("Skipped duplicate transaction event event_id=%s", event.event_id)
                return ProcessingResult.duplicate

            features = self.feature_processor.build(session, event)
            session.add(
                TransactionRecord(
                    id=event.data.transaction_id,
                    account_id=event.data.account_id,
                    merchant_id=event.data.merchant_id,
                    amount=event.data.amount,
                    currency=event.data.currency,
                    country=event.data.country,
                    status=event.data.status,
                    occurred_at=event.data.occurred_at,
                    device_id=event.data.device_id,
                    ip_address=event.data.ip_address,
                    payment_method=event.data.payment_method,
                    order_amount=event.data.order_amount,
                )
            )
            session.flush()
            self.feature_processor.store(session, event, features)
            session.add(
                ProcessedEventRecord(
                    event_id=event.event_id,
                    transaction_id=event.data.transaction_id,
                    event_type=event.event_type,
                )
            )

        logger.info(
            "Processed transaction event event_id=%s transaction_id=%s status=%s",
            event.event_id,
            event.data.transaction_id,
            event.data.status,
        )
        return ProcessingResult.processed
