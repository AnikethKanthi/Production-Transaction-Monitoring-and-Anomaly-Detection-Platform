"""Idempotent batch fixture loading; intentionally bypasses scoring/Kafka."""

import argparse
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from app.db.session import get_engine
from app.models import Transaction
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


def seed(engine, count=1000, batch_size=250, namespace="performance-fixture"):
    if count < 1 or not 1 <= batch_size <= 1000:
        raise ValueError("Positive count and batch size 1..1000 required")
    insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    statement = insert(Transaction).on_conflict_do_nothing(index_elements=["id"])
    anchor = datetime(2026, 1, 1, tzinfo=UTC)
    for start in range(0, count, batch_size):
        rows = [
            {
                "id": uuid5(NAMESPACE_URL, f"{namespace}:{i}"),
                "account_id": f"{namespace}-{i % 100}",
                "merchant_id": "fixture",
                "amount": Decimal(i % 10000 + 1) / 100,
                "currency": "USD",
                "country": "US",
                "status": "failed" if i % 10 == 0 else "completed",
                "occurred_at": anchor + timedelta(seconds=i),
            }
            for i in range(start, min(start + batch_size, count))
        ]
        with engine.begin() as connection:
            connection.execute(statement, rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--namespace", default="performance-fixture")
    args = parser.parse_args()
    seed(get_engine(), args.count, args.batch_size, args.namespace)
    print("Fixture batches committed; reruns preserve existing IDs.")
