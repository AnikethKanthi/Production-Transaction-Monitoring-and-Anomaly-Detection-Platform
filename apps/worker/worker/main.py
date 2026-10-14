import logging
import signal
from threading import Event

from worker.config import Settings
from worker.consumers.transaction_consumer import TransactionConsumer
from worker.logging import configure_logging
from worker.processors.transaction_processor import process_transaction


def run(stop: Event, settings: Settings, consumer: TransactionConsumer | None = None) -> None:
    logger = logging.getLogger(__name__)
    transaction_consumer = consumer or TransactionConsumer.from_settings(
        settings, processor=process_transaction
    )
    logger.info("Transaction consumer starting")
    transaction_consumer.run(stop)
    logger.info("Transaction consumer stopped")


def main() -> None:
    configure_logging()
    stop = Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    run(stop, Settings())


if __name__ == "__main__":
    main()
