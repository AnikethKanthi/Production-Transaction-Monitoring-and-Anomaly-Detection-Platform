import logging

from worker.events.transaction import TransactionEvent

logger = logging.getLogger(__name__)


def process_transaction(event: TransactionEvent) -> None:
    """Process one validated transaction event.

    Persistence and anomaly scoring are added behind this boundary in later milestones.
    """
    logger.info(
        "Processed transaction event event_id=%s transaction_id=%s status=%s",
        event.event_id,
        event.data.transaction_id,
        event.data.status,
    )
