import logging
import signal
from threading import Event

from worker.config import Settings
from worker.logging import configure_logging


def run(stop: Event, settings: Settings) -> None:
    logger = logging.getLogger(__name__)
    logger.info("Worker started in bootstrap mode; event processing is not configured")
    while not stop.wait(settings.worker_heartbeat_seconds):
        logger.info("Worker heartbeat")
    logger.info("Worker stopped")


def main() -> None:
    configure_logging()
    stop = Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    run(stop, Settings())


if __name__ == "__main__":
    main()
