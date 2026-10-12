from uuid import UUID

from sqlalchemy import select
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
        self, *, account_id: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[Transaction]:
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("limit must be 1..1000 and offset must be nonnegative")
        statement = select(Transaction)
        if account_id is not None:
            statement = statement.where(Transaction.account_id == account_id)
        statement = statement.order_by(Transaction.occurred_at.desc(), Transaction.id.desc())
        return list(self.session.scalars(statement.limit(limit).offset(offset)))
