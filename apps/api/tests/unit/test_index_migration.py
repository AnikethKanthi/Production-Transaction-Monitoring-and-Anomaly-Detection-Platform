import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def test_query_index_upgrade_downgrade_and_reupgrade():
    path = Path(__file__).resolve().parents[2] / "alembic/versions/0009_query_indexes.py"
    spec = importlib.util.spec_from_file_location("query_indexes", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE transactions (id TEXT, status TEXT, currency TEXT, occurred_at TEXT)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE alerts (id TEXT, status TEXT, created_at TEXT)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_transactions_status_occurred_at "
                "ON transactions (status, occurred_at)"
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                indexes = {
                    value["name"]: value["column_names"]
                    for value in inspect(connection).get_indexes("transactions")
                }
                assert indexes["ix_transactions_status_occurred_at"] == [
                    "status",
                    "occurred_at",
                    "id",
                ]
                assert indexes["ix_transactions_currency_occurred_at_id"] == [
                    "currency",
                    "occurred_at",
                    "id",
                ]
                migration.downgrade()
                indexes = inspect(connection).get_indexes("transactions")
                assert len(indexes) == 1 and indexes[0]["column_names"] == ["status", "occurred_at"]
                assert inspect(connection).get_indexes("alerts") == []
                migration.upgrade()
                assert len(inspect(connection).get_indexes("alerts")) == 1
    finally:
        engine.dispose()
