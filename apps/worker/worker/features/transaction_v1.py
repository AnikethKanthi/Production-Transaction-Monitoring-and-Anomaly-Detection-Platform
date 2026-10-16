from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from worker.events.transaction import TransactionData

FEATURE_DEFINITION_VERSION = "transaction_features.v1"
DECIMAL_PRECISION = Decimal("0.000001")


@dataclass(frozen=True)
class HistoricalTransaction:
    transaction_id: UUID
    amount: Decimal
    currency: str
    country: str
    status: str
    occurred_at: datetime
    device_id: str | None = None
    ip_address: str | None = None
    payment_method: str | None = None
    order_amount: Decimal | None = None


class TransactionFeatureVector(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    transaction_amount: float
    amount_difference_from_customer_average: float
    transactions_last_5_minutes: int
    transactions_last_hour: int
    decline_ratio: float
    country_change: int
    new_device_indicator: int
    new_ip_address_indicator: int
    unusual_transaction_time: int
    payment_method_frequency: float
    order_amount_deviation: float


def transform_transaction_features(
    current: TransactionData,
    history: Iterable[HistoricalTransaction],
) -> TransactionFeatureVector:
    prior = sorted(
        (item for item in history if item.occurred_at <= current.occurred_at),
        key=lambda item: (item.occurred_at, str(item.transaction_id)),
    )
    same_currency = [item for item in prior if item.currency == current.currency]
    average_amount = _average((item.amount for item in same_currency), current.amount)
    current_order_amount = current.order_amount or current.amount
    average_order_amount = _average(
        (item.order_amount or item.amount for item in same_currency), current_order_amount
    )
    five_minutes_ago = current.occurred_at - timedelta(minutes=5)
    one_hour_ago = current.occurred_at - timedelta(hours=1)
    decline_ratio = (
        Decimal(sum(item.status == "failed" for item in prior)) / Decimal(len(prior))
        if prior
        else Decimal(0)
    )
    latest = prior[-1] if prior else None
    payment_frequency = (
        Decimal(sum(item.payment_method == current.payment_method for item in prior))
        / Decimal(len(prior))
        if prior and current.payment_method is not None
        else Decimal(0)
    )

    return TransactionFeatureVector(
        transaction_amount=_number(current.amount),
        amount_difference_from_customer_average=_number(current.amount - average_amount),
        transactions_last_5_minutes=1 + sum(item.occurred_at >= five_minutes_ago for item in prior),
        transactions_last_hour=1 + sum(item.occurred_at >= one_hour_ago for item in prior),
        decline_ratio=_number(decline_ratio),
        country_change=int(latest is not None and latest.country != current.country),
        new_device_indicator=_new_value(current.device_id, (item.device_id for item in prior)),
        new_ip_address_indicator=_new_value(
            current.ip_address, (item.ip_address for item in prior)
        ),
        unusual_transaction_time=int(
            current.occurred_at.hour < 6 or current.occurred_at.hour >= 23
        ),
        payment_method_frequency=_number(payment_frequency),
        order_amount_deviation=_number(current_order_amount - average_order_amount),
    )


def _average(values: Iterable[Decimal], fallback: Decimal) -> Decimal:
    collected = tuple(values)
    return sum(collected, start=Decimal(0)) / Decimal(len(collected)) if collected else fallback


def _new_value(current: str | None, prior_values: Iterable[str | None]) -> int:
    if current is None:
        return 0
    return int(current not in set(prior_values))


def _number(value: Decimal) -> float:
    return float(value.quantize(DECIMAL_PRECISION, rounding=ROUND_HALF_EVEN))
