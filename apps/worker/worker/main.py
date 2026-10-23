import logging
import signal
from threading import Event

from prometheus_client import start_http_server
from redis import Redis

from worker.config import Settings
from worker.consumers.transaction_consumer import TransactionConsumer
from worker.logging import configure_logging
from worker.monitoring.rolling_metrics import RollingMetricsCounter
from worker.persistence.database import get_session_factory
from worker.processors.anomaly_processor import AnomalyProcessor
from worker.processors.transaction_processor import TransactionProcessor


def run(stop: Event, settings: Settings, consumer: TransactionConsumer | None = None) -> None:
    logger = logging.getLogger(__name__)
    anomaly_processor = AnomalyProcessor.load(settings.model_path, settings.model_metadata_path)
    metrics_counter = RollingMetricsCounter(
        Redis.from_url(settings.redis_url, decode_responses=True),
        settings.rolling_metrics_ttl_seconds,
    )
    transaction_consumer = consumer or TransactionConsumer.from_settings(
        settings,
        processor=TransactionProcessor(
            get_session_factory(settings),
            anomaly_processor=anomaly_processor,
            metrics_counter=metrics_counter,
        ).process,
    )
    logger.info("Transaction consumer starting")
    transaction_consumer.run(stop)
    logger.info("Transaction consumer stopped")


def main() -> None:
    configure_logging()
    settings = Settings()
    start_http_server(settings.metrics_port)
    stop = Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    run(stop, settings)


if __name__ == "__main__":
    main()
