from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.db.repositories.transactions import TransactionRepository
from app.models import Transaction
from app.schemas.transaction import TransactionCreate, TransactionStatus


class TransactionNotFoundError(Exception):
    def __init__(self, transaction_id: UUID) -> None:
        self.transaction_id = transaction_id


class TransactionService:
    def __init__(self, repository: TransactionRepository) -> None:
        self.repository = repository

    def create(self, payload: TransactionCreate) -> Transaction:
        return self.repository.add(Transaction(**payload.model_dump(mode="python")))

    def get(self, transaction_id: UUID) -> Transaction:
        transaction = self.repository.get(transaction_id)
        if transaction is None:
            raise TransactionNotFoundError(transaction_id)
        return transaction

    def list(
        self,
        *,
        status: TransactionStatus | None,
        country: str | None,
        currency: str | None,
        min_amount: Decimal | None,
        max_amount: Decimal | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Transaction], int]:
        return self.repository.list(
            status=status.value if status else None,
            country=country,
            currency=currency,
            min_amount=min_amount,
            max_amount=max_amount,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            limit=limit,
            offset=offset,
        )
