import logging
from typing import Protocol

from confluent_kafka import KafkaError, Producer

from worker.events.transaction import TransactionEvent, serialize_transaction_event
from worker.kafka.topics import TRANSACTIONS_TOPIC
from worker.logging import log_context

logger = logging.getLogger(__name__)


class ProducerClient(Protocol):
    def produce(self, topic: str, **kwargs: object) -> None: ...

    def flush(self, timeout: float | None = None) -> int: ...


class EventDeliveryError(RuntimeError):
    pass


class TransactionEventProducer:
    def __init__(self, producer: ProducerClient, *, delivery_timeout: float = 10) -> None:
        self.producer = producer
        self.delivery_timeout = delivery_timeout

    @classmethod
    def connect(cls, bootstrap_servers: str) -> "TransactionEventProducer":
        return cls(Producer({"bootstrap.servers": bootstrap_servers}))

    def publish(self, event: TransactionEvent) -> None:
        correlation = (
            event.correlation_id or log_context.get().get("correlation_id") or str(event.event_id)
        )
        event = event.model_copy(update={"correlation_id": correlation})
        errors: list[KafkaError] = []

        def delivered(error: KafkaError | None, _message: object) -> None:
            if error is not None:
                errors.append(error)

        self.producer.produce(
            TRANSACTIONS_TOPIC,
            key=str(event.data.transaction_id).encode(),
            value=serialize_transaction_event(event),
            headers={
                "content-type": "application/json",
                "event-version": "1",
                "x-correlation-id": correlation,
            },
            on_delivery=delivered,
        )
        remaining = self.producer.flush(self.delivery_timeout)
        if remaining:
            raise EventDeliveryError(
                f"{remaining} Kafka event(s) were not delivered before timeout"
            )
        if errors:
            raise EventDeliveryError(f"Kafka rejected the transaction event: {errors[0]}")
        logger.info(
            "Kafka transaction published",
            extra={
                "correlation_id": correlation,
                "event_id": str(event.event_id),
                "transaction_id": str(event.data.transaction_id),
                "topic": TRANSACTIONS_TOPIC,
            },
        )

    def close(self) -> None:
        remaining = self.producer.flush(self.delivery_timeout)
        if remaining:
            raise EventDeliveryError(f"{remaining} Kafka event(s) remain undelivered")
