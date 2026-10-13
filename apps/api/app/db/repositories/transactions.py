from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Transaction


class TransactionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, transaction: Transaction) -> Transaction:
        self.session.add(transaction)
        self.session.flush()
        return transaction

    def get(self, transaction_id: UUID) -> Transaction | None:
        return self.session.get(Transaction, transaction_id)

    def list(
        self,
        *,
        account_id: str | None = None,
        status: str | None = None,
        country: str | None = None,
        currency: str | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Transaction], int]:
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("limit must be 1..1000 and offset must be nonnegative")
        statement = self._filtered_statement(
            account_id=account_id,
            status=status,
            country=country,
            currency=currency,
            min_amount=min_amount,
            max_amount=max_amount,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        total = self.session.scalar(count_statement) or 0
        statement = statement.order_by(Transaction.occurred_at.desc(), Transaction.id.desc())
        items = list(self.session.scalars(statement.limit(limit).offset(offset)))
        return items, total

    @staticmethod
    def _filtered_statement(
        *,
        account_id: str | None,
        status: str | None,
        country: str | None,
        currency: str | None,
        min_amount: Decimal | None,
        max_amount: Decimal | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
    ) -> Select[tuple[Transaction]]:
        statement = select(Transaction)
        filters = (
            (account_id, Transaction.account_id),
            (status, Transaction.status),
            (country, Transaction.country),
            (currency, Transaction.currency),
        )
        for value, column in filters:
            if value is not None:
                statement = statement.where(column == value)
        if min_amount is not None:
            statement = statement.where(Transaction.amount >= min_amount)
        if max_amount is not None:
            statement = statement.where(Transaction.amount <= max_amount)
        if occurred_from is not None:
            statement = statement.where(Transaction.occurred_at >= occurred_from)
        if occurred_to is not None:
            statement = statement.where(Transaction.occurred_at <= occurred_to)
        return statement
