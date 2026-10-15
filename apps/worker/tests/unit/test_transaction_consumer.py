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
    result.key.return_value = b"transaction-key"
    return result


def test_valid_event_is_processed_then_committed() -> None:
    client = Mock()
    processor = Mock()
    dead_letter = Mock()
    kafka_message = message(event_payload())

    TransactionConsumer(client, processor, dead_letter)._handle(kafka_message)

    processor.assert_called_once()
    dead_letter.assert_not_called()
    client.commit.assert_called_once_with(message=kafka_message, asynchronous=False)


def test_invalid_event_is_skipped_and_committed(caplog) -> None:
    client = Mock()
    processor = Mock()
    dead_letter = Mock()
    kafka_message = message(b'{"not":"a transaction"}')

    TransactionConsumer(client, processor, dead_letter)._handle(kafka_message)

    processor.assert_not_called()
    dead_letter.assert_called_once()
    assert dead_letter.call_args.args[0].attempts == 1
    assert dead_letter.call_args.args[0].original_key_base64 == "dHJhbnNhY3Rpb24ta2V5"
    client.commit.assert_called_once_with(message=kafka_message, asynchronous=False)
    assert "Rejected invalid transaction event" in caplog.text


def test_processor_failure_is_retried_then_dead_lettered() -> None:
    client = Mock()
    processor = Mock(side_effect=RuntimeError("processing failed"))
    dead_letter = Mock()
    sleeper = Mock()
    kafka_message = message(event_payload())

    TransactionConsumer(
        client,
        processor,
        dead_letter,
        max_processing_attempts=3,
        retry_backoff_seconds=0.1,
        sleeper=sleeper,
    )._handle(kafka_message)

    assert processor.call_count == 3
    assert [call.args[0] for call in sleeper.call_args_list] == [0.1, 0.2]
    assert dead_letter.call_args.args[0].attempts == 3
    client.commit.assert_called_once_with(message=kafka_message, asynchronous=False)


def test_dead_letter_failure_does_not_commit() -> None:
    client = Mock()
    dead_letter = Mock(side_effect=RuntimeError("Kafka unavailable"))
    kafka_message = message(b"invalid")

    try:
        TransactionConsumer(client, Mock(), dead_letter)._handle(kafka_message)
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
    TransactionConsumer(client, Mock(), Mock(), poll_timeout=0.01).run(stop)

    client.subscribe.assert_called_once_with([TRANSACTIONS_TOPIC])
    client.close.assert_called_once_with()
