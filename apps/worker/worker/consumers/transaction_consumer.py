import logging
import time
from collections.abc import Callable
from threading import Event
from typing import Protocol
from uuid import UUID

from confluent_kafka import Consumer, KafkaError, KafkaException, Message

from worker.config import Settings
from worker.events.dead_letter import DeadLetterEvent
from worker.events.transaction import TransactionEvent, deserialize_transaction_event
from worker.kafka.dead_letter_producer import DeadLetterProducer
from worker.kafka.topics import TRANSACTIONS_TOPIC
from worker.logging import event_context
from worker.monitoring.metrics import (
    WORKER_EVENTS,
    WORKER_LATENCY,
    WORKER_RETRIES,
    kafka_statistics,
)

logger = logging.getLogger(__name__)


class ConsumerClient(Protocol):
    def subscribe(self, topics: list[str]) -> None: ...

    def poll(self, timeout: float) -> Message | None: ...

    def commit(self, message: Message, asynchronous: bool = False) -> object: ...

    def close(self) -> None: ...


class TransactionConsumer:
    def __init__(
        self,
        consumer: ConsumerClient,
        processor: Callable[[TransactionEvent], object],
        dead_letter_publisher: Callable[[DeadLetterEvent], None],
        *,
        poll_timeout: float = 1,
        max_processing_attempts: int = 3,
        retry_backoff_seconds: float = 0.5,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.consumer = consumer
        self.processor = processor
        self.dead_letter_publisher = dead_letter_publisher
        self.poll_timeout = poll_timeout
        self.max_processing_attempts = max_processing_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleeper = sleeper

    @classmethod
    def from_settings(
        cls, settings: Settings, processor: Callable[[TransactionEvent], object]
    ) -> "TransactionConsumer":
        consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": settings.kafka_consumer_group,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
                "statistics.interval.ms": 10000,
                "stats_cb": kafka_statistics,
            }
        )
        dead_letter_producer = DeadLetterProducer.connect(settings.kafka_bootstrap_servers)
        return cls(
            consumer,
            processor,
            dead_letter_producer.publish,
            poll_timeout=settings.kafka_poll_timeout_seconds,
            max_processing_attempts=settings.kafka_max_processing_attempts,
            retry_backoff_seconds=settings.kafka_retry_backoff_seconds,
        )

    def run(self, stop: Event) -> None:
        self.consumer.subscribe([TRANSACTIONS_TOPIC])
        try:
            while not stop.is_set():
                message = self.consumer.poll(self.poll_timeout)
                if message is None:
                    continue
                if message.error():
                    if message.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise KafkaException(message.error())
                self._handle(message)
        finally:
            self.consumer.close()

    def _handle(self, message: Message) -> None:
        with WORKER_LATENCY.time():
            self._handle_message(message)

    def _handle_message(self, message: Message) -> None:
        payload = self._payload_bytes(message.value())
        try:
            event = deserialize_transaction_event(payload)
        except (ValueError, TypeError) as error:
            logger.warning(
                "Rejected invalid transaction event topic=%s partition=%s offset=%s error=%s",
                message.topic(),
                message.partition(),
                message.offset(),
                type(error).__name__,
            )
            self._publish_dead_letter(message, payload, error, attempts=1)
            self.consumer.commit(message=message, asynchronous=False)
            WORKER_EVENTS.labels(outcome="rejected").inc()
            return

        with event_context(event):
            logger.info(
                "Kafka transaction received",
                extra={
                    "topic": TRANSACTIONS_TOPIC,
                    "partition": message.partition(),
                    "offset": message.offset(),
                },
            )
            try:
                self._process_event(event, message, payload)
            except Exception:
                logger.exception("Kafka transaction handling failed before completion")
                raise

    def _process_event(self, event, message, payload):

        for attempt in range(1, self.max_processing_attempts + 1):
            try:
                result = self.processor(event)
                outcome = "duplicate" if result == "duplicate" else "processed"
            except Exception as error:
                WORKER_RETRIES.inc()
                logger.exception(
                    "Transaction processing failed event_id=%s attempt=%s/%s",
                    event.event_id,
                    attempt,
                    self.max_processing_attempts,
                )
                if attempt < self.max_processing_attempts:
                    self.sleeper(self.retry_backoff_seconds * (2 ** (attempt - 1)))
                    continue
                self._publish_dead_letter(
                    message, payload, error, attempts=attempt, event_id=event.event_id
                )
                outcome = "dead_lettered"
            self.consumer.commit(message=message, asynchronous=False)
            WORKER_EVENTS.labels(outcome=outcome).inc()
            logger.info("Kafka transaction handled: %s", outcome)
            return

    def _publish_dead_letter(
        self,
        message: Message,
        payload: bytes,
        error: Exception,
        *,
        attempts: int,
        event_id: UUID | None = None,
    ) -> None:
        dead_letter = DeadLetterEvent.from_message(
            topic=message.topic(),
            partition=message.partition(),
            offset=message.offset(),
            key=self._key_bytes(message.key()),
            payload=payload,
            event_id=event_id,
            attempts=attempts,
            error=error,
        )
        self.dead_letter_publisher(dead_letter)

    @staticmethod
    def _payload_bytes(payload: bytes | str | None) -> bytes:
        if payload is None:
            return b""
        return payload if isinstance(payload, bytes) else payload.encode("utf-8")

    @staticmethod
    def _key_bytes(key: bytes | str | None) -> bytes | None:
        if key is None:
            return None
        return key if isinstance(key, bytes) else key.encode("utf-8")
