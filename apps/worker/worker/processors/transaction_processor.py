import logging
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from worker.events.transaction import TransactionEvent
from worker.persistence.models import ProcessedEventRecord, TransactionRecord

logger = logging.getLogger(__name__)


class ProcessingResult(StrEnum):
    processed = "processed"
    duplicate = "duplicate"


class TransactionProcessor:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

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
                )
            )
            session.flush()
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
