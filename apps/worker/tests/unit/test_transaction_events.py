from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from worker.events.transaction import (
    TransactionData,
    TransactionEvent,
    deserialize_transaction_event,
    serialize_transaction_event,
)
from worker.kafka.producer import EventDeliveryError, TransactionEventProducer
from worker.kafka.topics import TRANSACTIONS_TOPIC


def event() -> TransactionEvent:
    now = datetime.now(UTC)
    return TransactionEvent(
        produced_at=now,
        data=TransactionData(
            transaction_id=uuid4(),
            account_id="acct-1",
            merchant_id="merchant-1",
            amount=Decimal("49.95"),
            currency="USD",
            country="US",
            status="completed",
            occurred_at=now,
        ),
    )


def test_event_round_trip() -> None:
    original = event()
    assert deserialize_transaction_event(serialize_transaction_event(original)) == original


@pytest.mark.parametrize(
    "change",
    [
        {"event_version": 2},
        {"event_type": "transaction.updated"},
        {"data": {"amount": "-1.00"}},
        {"data": {"currency": "usd"}},
        {"data": {"unknown": "field"}},
    ],
)
def test_invalid_event_is_rejected(change: dict) -> None:
    payload = event().model_dump(mode="json")
    if "data" in change:
        payload["data"].update(change["data"])
    else:
        payload.update(change)
    with pytest.raises(ValidationError):
        TransactionEvent.model_validate(payload)


def test_deserializer_rejects_empty_and_non_utf8_payloads() -> None:
    with pytest.raises(ValueError, match="empty"):
        deserialize_transaction_event(None)
    with pytest.raises(ValueError, match="UTF-8"):
        deserialize_transaction_event(b"\xff")


def test_producer_uses_transaction_id_as_partition_key() -> None:
    client = Mock()
    client.flush.return_value = 0
    transaction_event = event()

    TransactionEventProducer(client).publish(transaction_event)

    _, kwargs = client.produce.call_args
    assert client.produce.call_args.args == (TRANSACTIONS_TOPIC,)
    assert kwargs["key"] == str(transaction_event.data.transaction_id).encode()
    assert deserialize_transaction_event(kwargs["value"]) == transaction_event


def test_producer_reports_delivery_timeout() -> None:
    client = Mock()
    client.flush.return_value = 1
    with pytest.raises(EventDeliveryError, match="not delivered"):
        TransactionEventProducer(client).publish(event())
