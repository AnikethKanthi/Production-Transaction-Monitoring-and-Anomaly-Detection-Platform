from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class TransactionStatus(StrEnum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"


class TransactionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: UUID
    account_id: Identifier
    merchant_id: Identifier | None = None
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: CurrencyCode
    country: CountryCode
    status: TransactionStatus
    occurred_at: datetime
    device_id: Identifier | None = None
    ip_address: Identifier | None = None
    payment_method: Identifier | None = None
    order_amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value


class TransactionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    event_type: Literal["transaction.created"] = "transaction.created"
    event_version: Literal[1] = 1
    produced_at: datetime
    correlation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,128}$")
    data: TransactionData

    @field_validator("produced_at")
    @classmethod
    def produced_at_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("produced_at must include a timezone offset")
        return value


def serialize_transaction_event(event: TransactionEvent) -> bytes:
    return event.model_dump_json().encode("utf-8")


def deserialize_transaction_event(payload: bytes | str | None) -> TransactionEvent:
    if payload is None:
        raise ValueError("event payload is empty")
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("event payload is not valid UTF-8") from error
    return TransactionEvent.model_validate_json(payload)
