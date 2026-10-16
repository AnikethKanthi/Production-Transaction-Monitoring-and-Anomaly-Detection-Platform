from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from worker.events.transaction import TransactionData
from worker.features.transaction_v1 import (
    FEATURE_DEFINITION_VERSION,
    HistoricalTransaction,
    transform_transaction_features,
)


def current(**overrides: object) -> TransactionData:
    values = {
        "transaction_id": uuid4(),
        "account_id": "acct-1",
        "amount": Decimal("150.00"),
        "currency": "USD",
        "country": "CA",
        "status": "completed",
        "occurred_at": datetime(2026, 10, 16, 12, tzinfo=UTC),
        "device_id": "device-2",
        "ip_address": "198.51.100.2",
        "payment_method": "card",
        "order_amount": Decimal("180.00"),
    }
    return TransactionData.model_validate(values | overrides)


def historical(
    *,
    minutes_ago: int,
    amount: str,
    currency: str = "USD",
    country: str = "US",
    status: str = "completed",
    device_id: str | None = "device-1",
    ip_address: str | None = "198.51.100.1",
    payment_method: str | None = "card",
    order_amount: str | None = None,
) -> HistoricalTransaction:
    return HistoricalTransaction(
        transaction_id=UUID(int=abs(minutes_ago) + 1),
        amount=Decimal(amount),
        currency=currency,
        country=country,
        status=status,
        occurred_at=datetime(2026, 10, 16, 12, tzinfo=UTC) - timedelta(minutes=minutes_ago),
        device_id=device_id,
        ip_address=ip_address,
        payment_method=payment_method,
        order_amount=Decimal(order_amount) if order_amount else None,
    )


def test_feature_definition_is_versioned_and_deterministic() -> None:
    transaction = current()
    history = [
        historical(minutes_ago=2, amount="100", status="failed", order_amount="120"),
        historical(
            minutes_ago=30,
            amount="200",
            ip_address="198.51.100.2",
            payment_method="bank",
            order_amount="200",
        ),
        historical(
            minutes_ago=120,
            amount="500",
            currency="EUR",
            country="CA",
            status="failed",
            device_id="device-2",
        ),
    ]

    first = transform_transaction_features(transaction, history)
    second = transform_transaction_features(transaction, reversed(history))

    assert FEATURE_DEFINITION_VERSION == "transaction_features.v1"
    assert first == second
    assert first.model_dump() == {
        "transaction_amount": 150.0,
        "amount_difference_from_customer_average": 0.0,
        "transactions_last_5_minutes": 2,
        "transactions_last_hour": 3,
        "decline_ratio": 0.666667,
        "country_change": 1,
        "new_device_indicator": 0,
        "new_ip_address_indicator": 0,
        "unusual_transaction_time": 0,
        "payment_method_frequency": 0.666667,
        "order_amount_deviation": 20.0,
    }


def test_missing_history_and_optional_values_use_safe_defaults() -> None:
    features = transform_transaction_features(
        current(
            amount="10.00",
            occurred_at="2026-10-16T02:00:00Z",
            device_id=None,
            ip_address=None,
            payment_method=None,
            order_amount=None,
        ),
        [],
    )

    assert features.model_dump() == {
        "transaction_amount": 10.0,
        "amount_difference_from_customer_average": 0.0,
        "transactions_last_5_minutes": 1,
        "transactions_last_hour": 1,
        "decline_ratio": 0.0,
        "country_change": 0,
        "new_device_indicator": 0,
        "new_ip_address_indicator": 0,
        "unusual_transaction_time": 1,
        "payment_method_frequency": 0.0,
        "order_amount_deviation": 0.0,
    }


def test_future_history_is_ignored() -> None:
    transaction = current()
    future = historical(minutes_ago=-1, amount="999999")
    assert transform_transaction_features(transaction, [future]) == transform_transaction_features(
        transaction, []
    )
