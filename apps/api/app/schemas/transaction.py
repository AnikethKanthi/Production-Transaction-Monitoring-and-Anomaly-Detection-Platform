from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class TransactionStatus(StrEnum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class TransactionCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "account_id": "acct_42",
                    "merchant_id": "merchant_17",
                    "amount": "149.95",
                    "currency": "USD",
                    "country": "US",
                    "status": "pending",
                    "occurred_at": "2026-10-13T14:30:00Z",
                    "device_id": "device_8",
                    "ip_address": "203.0.113.8",
                    "payment_method": "card",
                    "order_amount": "149.95",
                }
            ]
        }
    )

    account_id: Identifier
    merchant_id: Identifier | None = None
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: CurrencyCode
    country: CountryCode
    status: TransactionStatus = TransactionStatus.pending
    occurred_at: datetime
    device_id: Identifier | None = None
    ip_address: Identifier | None = None
    payment_method: Identifier | None = None
    order_amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)

    @model_validator(mode="after")
    def require_timezone(self) -> "TransactionCreate":
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        return self


class TransactionFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TransactionStatus | None = None
    country: CountryCode | None = None
    currency: CurrencyCode | None = None
    min_amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    max_amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("occurred_from", "occurred_to")
    @classmethod
    def dates_require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("date filters must include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_ranges(self) -> "TransactionFilters":
        if self.min_amount is not None and self.max_amount is not None:
            if self.min_amount > self.max_amount:
                raise ValueError("min_amount must be less than or equal to max_amount")
        if self.occurred_from is not None and self.occurred_to is not None:
            if self.occurred_from > self.occurred_to:
                raise ValueError("occurred_from must be before or equal to occurred_to")
        return self


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: str
    merchant_id: str | None
    amount: Decimal
    currency: str
    country: str
    status: TransactionStatus
    occurred_at: datetime
    created_at: datetime
    device_id: str | None
    ip_address: str | None
    payment_method: str | None
    order_amount: Decimal | None


class PaginationMeta(BaseModel):
    limit: int
    offset: int
    total: int


class TransactionList(BaseModel):
    items: list[TransactionRead]
    pagination: PaginationMeta


class ErrorDetail(BaseModel):
    type: str | None = None
    loc: list[str | int] | None = None
    msg: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
