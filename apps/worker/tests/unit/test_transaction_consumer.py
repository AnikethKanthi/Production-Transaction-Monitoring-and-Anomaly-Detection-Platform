from datetime import UTC, datetime
from decimal import Decimal
from threading import Event
from unittest.mock import Mock
from uuid import uuid4

from worker.consumers.transaction_consumer import TransactionConsumer
from worker.events.transaction import TransactionData, TransactionEvent, serialize_transaction_event
from worker.kafka.topics import TRANSACTIONS_TOPIC


def event_payload() -> bytes:
    now = datetime.now(UTC)
    return serialize_transaction_event(
        TransactionEvent(
            produced_at=now,
            data=TransactionData(
                transaction_id=uuid4(),
                account_id="acct-1",
                amount=Decimal("10.00"),
                currency="USD",
                country="US",
                status="completed",
                occurred_at=now,
            ),
        )
    )


def message(payload: bytes) -> Mock:
    result = Mock()
    result.error.return_value = None
    result.value.return_value = payload
    result.topic.return_value = TRANSACTIONS_TOPIC
    result.partition.return_value = 0
    result.offset.return_value = 1
    return result


def test_valid_event_is_processed_then_committed() -> None:
    client = Mock()
    processor = Mock()
    kafka_message = message(event_payload())

    TransactionConsumer(client, processor)._handle(kafka_message)

    processor.assert_called_once()
    client.commit.assert_called_once_with(message=kafka_message, asynchronous=False)


def test_invalid_event_is_skipped_and_committed(caplog) -> None:
    client = Mock()
    processor = Mock()
    kafka_message = message(b'{"not":"a transaction"}')

    TransactionConsumer(client, processor)._handle(kafka_message)

    processor.assert_not_called()
    client.commit.assert_called_once_with(message=kafka_message, asynchronous=False)
    assert "Rejected invalid transaction event" in caplog.text


def test_processor_failure_does_not_commit() -> None:
    client = Mock()
    processor = Mock(side_effect=RuntimeError("processing failed"))
    kafka_message = message(event_payload())

    try:
        TransactionConsumer(client, processor)._handle(kafka_message)
    except RuntimeError:
        pass

    client.commit.assert_not_called()


def test_shutdown_closes_consumer() -> None:
    stop = Event()
    client = Mock()

    def poll(_timeout: float) -> None:
        stop.set()
        return None

    client.poll.side_effect = poll
    TransactionConsumer(client, Mock(), poll_timeout=0.01).run(stop)

    client.subscribe.assert_called_once_with([TRANSACTIONS_TOPIC])
    client.close.assert_called_once_with()
