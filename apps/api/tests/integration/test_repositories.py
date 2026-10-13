from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db import session as session_module
from app.db.repositories.processed_events import ProcessedEventRepository
from app.db.repositories.transactions import TransactionRepository
from app.models import ProcessedEvent, Transaction

pytestmark = pytest.mark.integration


def transaction(**overrides) -> Transaction:
    values = {
        "account_id": "account-1",
        "merchant_id": "merchant-1",
        "amount": Decimal("123.45"),
        "currency": "USD",
        "country": "US",
        "occurred_at": datetime(2026, 1, 1, 12, tzinfo=UTC),
    }
    return Transaction(**(values | overrides))


def test_insert_and_retrieve_in_new_session(migrated_connection: Connection) -> None:
    factory = sessionmaker(migrated_connection, expire_on_commit=False)
    with factory.begin() as session:
        saved = TransactionRepository(session).add(transaction())
        transaction_id = saved.id
    with factory() as session:
        repo = TransactionRepository(session)
        fetched = repo.get(transaction_id)
        assert fetched is not None
        assert fetched.amount == Decimal("123.45")
        assert fetched.currency == "USD"
        assert fetched.status == "pending"
        assert fetched.created_at.tzinfo is not None
        assert fetched.occurred_at == datetime(2026, 1, 1, 12, tzinfo=UTC)
        assert repo.get(uuid4()) is None


def test_filter_and_pagination(migrated_connection: Connection) -> None:
    factory = sessionmaker(migrated_connection, expire_on_commit=False)
    with factory.begin() as session:
        repo = TransactionRepository(session)
        first = repo.add(transaction())
        second = repo.add(transaction(occurred_at=first.occurred_at + timedelta(seconds=1)))
        repo.add(transaction(account_id="account-2"))
        items, total = repo.list(account_id="account-1")
        assert total == 2
        assert [row.id for row in items] == [second.id, first.id]
        items, total = repo.list(account_id="account-1", limit=1, offset=1)
        assert total == 2
        assert [row.id for row in items] == [first.id]
        assert repo.list(account_id="missing") == ([], 0)
        with pytest.raises(ValueError):
            repo.list(limit=0)


def test_duplicate_event_rolls_back_whole_unit_of_work(migrated_connection: Connection) -> None:
    factory = sessionmaker(migrated_connection, expire_on_commit=False)
    event_id = uuid4()
    with factory.begin() as session:
        saved = TransactionRepository(session).add(transaction())
        ProcessedEventRepository(session).add(
            ProcessedEvent(
                event_id=event_id, transaction_id=saved.id, event_type="transaction.created.v1"
            )
        )
        original_id = saved.id
    duplicate_transaction_id = uuid4()
    with pytest.raises(IntegrityError) as error:
        with factory.begin() as session:
            TransactionRepository(session).add(transaction(id=duplicate_transaction_id))
            ProcessedEventRepository(session).add(
                ProcessedEvent(
                    event_id=event_id,
                    transaction_id=duplicate_transaction_id,
                    event_type="transaction.updated.v1",
                )
            )
    assert error.value.orig.sqlstate == "23505"
    with factory() as session:
        event = ProcessedEventRepository(session).get(event_id)
        assert event is not None
        assert event.transaction_id == original_id
        assert event.processed_at.tzinfo is not None
        assert TransactionRepository(session).get(duplicate_transaction_id) is None


@pytest.mark.parametrize(
    "invalid",
    [
        {"amount": Decimal("0.00")},
        {"amount": Decimal("-1.00")},
        {"currency": "usd"},
        {"currency": "US"},
        {"currency": "123"},
        {"country": "us"},
        {"status": "unknown"},
    ],
)
def test_invalid_transaction_rejected(migrated_connection: Connection, invalid: dict) -> None:
    factory = sessionmaker(migrated_connection)
    with pytest.raises(IntegrityError) as error:
        with factory.begin() as session:
            TransactionRepository(session).add(transaction(**invalid))
    assert error.value.orig.sqlstate == "23514"


def test_event_requires_existing_transaction(migrated_connection: Connection) -> None:
    factory = sessionmaker(migrated_connection)
    with pytest.raises(IntegrityError) as error:
        with factory.begin() as session:
            ProcessedEventRepository(session).add(
                ProcessedEvent(
                    event_id=uuid4(), transaction_id=uuid4(), event_type="transaction.created.v1"
                )
            )
    assert error.value.orig.sqlstate == "23503"


def test_session_dependency_commits_and_rolls_back(
    migrated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = sessionmaker(migrated_connection, expire_on_commit=False)
    monkeypatch.setattr(session_module, "get_session_factory", lambda: factory)
    session_scope = contextmanager(session_module.get_session)
    with session_scope() as session:
        saved = TransactionRepository(session).add(transaction())
        saved_id = saved.id
    failed_id = uuid4()
    with pytest.raises(RuntimeError, match="processing failed"):
        with session_scope() as session:
            TransactionRepository(session).add(transaction(id=failed_id))
            raise RuntimeError("processing failed")
    with factory() as session:
        repo = TransactionRepository(session)
        assert repo.get(saved_id) is not None
        assert repo.get(failed_id) is None
