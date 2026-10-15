from confluent_kafka import Producer

from worker.events.dead_letter import DeadLetterEvent, serialize_dead_letter_event
from worker.kafka.producer import EventDeliveryError, ProducerClient
from worker.kafka.topics import TRANSACTIONS_DEAD_LETTER_TOPIC


class DeadLetterProducer:
    def __init__(self, producer: ProducerClient, *, delivery_timeout: float = 10) -> None:
        self.producer = producer
        self.delivery_timeout = delivery_timeout

    @classmethod
    def connect(cls, bootstrap_servers: str) -> "DeadLetterProducer":
        return cls(Producer({"bootstrap.servers": bootstrap_servers}))

    def publish(self, event: DeadLetterEvent) -> None:
        errors: list[object] = []

        def delivered(error: object | None, _message: object) -> None:
            if error is not None:
                errors.append(error)

        self.producer.produce(
            TRANSACTIONS_DEAD_LETTER_TOPIC,
            key=str(event.dead_letter_id).encode(),
            value=serialize_dead_letter_event(event),
            headers={"content-type": "application/json", "event-version": "1"},
            on_delivery=delivered,
        )
        remaining = self.producer.flush(self.delivery_timeout)
        if remaining:
            raise EventDeliveryError(
                f"{remaining} dead-letter event(s) were not delivered before timeout"
            )
        if errors:
            raise EventDeliveryError(f"Kafka rejected the dead-letter event: {errors[0]}")
