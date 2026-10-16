import pytest
from alembic.config import Config
from sqlalchemy import Connection, inspect, text

from alembic import command

pytestmark = pytest.mark.integration


def test_upgrade_downgrade_and_upgrade_again(
    alembic_config: Config, database_connection: Connection
) -> None:
    command.upgrade(alembic_config, "head")
    inspector = inspect(database_connection)
    assert set(inspector.get_table_names()) == {
        "transactions",
        "processed_events",
        "inference_features",
        "alembic_version",
    }
    assert database_connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
    database_connection.commit()
    command.check(alembic_config)
    database_connection.commit()
    command.downgrade(alembic_config, "base")
    assert set(inspect(database_connection).get_table_names()) == {"alembic_version"}
    database_connection.commit()
    command.upgrade(alembic_config, "head")
    command.upgrade(alembic_config, "head")  # Already at head is a no-op.
    assert "transactions" in inspect(database_connection).get_table_names()


def test_indexes_and_event_primary_key(migrated_connection: Connection) -> None:
    inspector = inspect(migrated_connection)
    indexes = {
        index["name"]: index["column_names"] for index in inspector.get_indexes("transactions")
    }
    assert indexes == {
        "ix_transactions_occurred_at_id": ["occurred_at", "id"],
        "ix_transactions_account_id_occurred_at": ["account_id", "occurred_at"],
        "ix_transactions_status_occurred_at": ["status", "occurred_at"],
        "ix_transactions_country_occurred_at": ["country", "occurred_at"],
    }
    assert inspector.get_pk_constraint("processed_events")["constrained_columns"] == ["event_id"]
    assert {index["name"] for index in inspector.get_indexes("processed_events")} == {
        "ix_processed_events_transaction_id",
        "ix_processed_events_processed_at",
    }
    foreign_key = inspector.get_foreign_keys("processed_events")[0]
    assert foreign_key["referred_table"] == "transactions"
    assert foreign_key["options"]["ondelete"] == "RESTRICT"
    assert {index["name"] for index in inspector.get_indexes("inference_features")} == {
        "ix_inference_features_event_id",
        "ix_inference_features_transaction_id",
        "uq_inference_features_version",
    }
    feature_foreign_key = inspector.get_foreign_keys("inference_features")[0]
    assert feature_foreign_key["referred_table"] == "transactions"
    assert feature_foreign_key["options"]["ondelete"] == "CASCADE"
