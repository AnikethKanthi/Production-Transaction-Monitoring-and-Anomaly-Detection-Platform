import logging
from collections.abc import Callable
from threading import Event
from typing import Protocol

from confluent_kafka import Consumer, KafkaError, KafkaException, Message

from worker.config import Settings
from worker.events.transaction import TransactionEvent, deserialize_transaction_event
from worker.kafka.topics import TRANSACTIONS_TOPIC

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
        processor: Callable[[TransactionEvent], None],
        *,
        poll_timeout: float = 1,
    ) -> None:
        self.consumer = consumer
        self.processor = processor
        self.poll_timeout = poll_timeout

    @classmethod
    def from_settings(
        cls, settings: Settings, processor: Callable[[TransactionEvent], None]
    ) -> "TransactionConsumer":
        consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": settings.kafka_consumer_group,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        return cls(consumer, processor, poll_timeout=settings.kafka_poll_timeout_seconds)

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
        try:
            event = deserialize_transaction_event(message.value())
        except (ValueError, TypeError) as error:
            logger.warning(
                "Rejected invalid transaction event topic=%s partition=%s offset=%s error=%s",
                message.topic(),
                message.partition(),
                message.offset(),
                error,
            )
            self.consumer.commit(message=message, asynchronous=False)
            return

        self.processor(event)
        self.consumer.commit(message=message, asynchronous=False)
