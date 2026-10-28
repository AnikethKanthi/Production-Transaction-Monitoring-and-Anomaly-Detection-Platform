from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Connection, MetaData, Table, inspect, select, text

from alembic import command

pytestmark = pytest.mark.integration


def test_existing_alert_gets_import_audit(alembic_config, database_connection):
    command.upgrade(alembic_config, "0006")
    metadata = MetaData()
    transactions = Table("transactions", metadata, autoload_with=database_connection)
    anomalies = Table("anomalies", metadata, autoload_with=database_connection)
    alerts = Table("alerts", metadata, autoload_with=database_connection)
    transaction_id, anomaly_id, alert_id = uuid4(), uuid4(), uuid4()
    database_connection.execute(
        transactions.insert().values(
            id=transaction_id,
            account_id="migration-test",
            amount=100,
            currency="USD",
            country="US",
            status="completed",
            occurred_at=datetime.now(UTC),
        )
    )
    database_connection.execute(
        anomalies.insert().values(
            id=anomaly_id,
            transaction_id=transaction_id,
            score=0.4,
            model_version="test.v1",
            scoring_status="scored",
            inference_latency_seconds=0.01,
        )
    )
    database_connection.execute(
        alerts.insert().values(
            id=alert_id,
            transaction_id=transaction_id,
            anomaly_id=anomaly_id,
            event_id=uuid4(),
            severity="high",
            policy_version="test.v1",
            model_version="test.v1",
            evidence={},
        )
    )
    database_connection.commit()
    command.upgrade(alembic_config, "head")
    audit = Table("alert_audit", MetaData(), autoload_with=database_connection)
    imported = database_connection.execute(select(audit)).mappings().one()
    assert imported["alert_id"] == alert_id
    assert imported["action"] == "import"
    assert imported["version"] == 1
    assert imported["after"] == {"status": "open", "assignee": None, "version": 1}


def test_upgrade_downgrade_and_upgrade_again(
    alembic_config: Config, database_connection: Connection
) -> None:
    command.upgrade(alembic_config, "head")
    inspector = inspect(database_connection)
    assert set(inspector.get_table_names()) == {
        "transactions",
        "processed_events",
        "inference_features",
        "anomalies",
        "alerts",
        "alert_audit",
        "alembic_version",
    }
    assert database_connection.scalar(text("SELECT version_num FROM alembic_version")) == "0007"
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
    assert {index["name"] for index in inspector.get_indexes("anomalies")} == {
        "ix_anomalies_created_at",
        "ix_anomalies_model_version",
        "uq_anomalies_transaction_id",
    }
    anomaly_foreign_key = inspector.get_foreign_keys("anomalies")[0]
    assert anomaly_foreign_key["referred_table"] == "transactions"
    assert anomaly_foreign_key["options"]["ondelete"] == "CASCADE"
    assert {item["name"] for item in inspector.get_indexes("alerts")} == {
        "ix_alerts_transaction_id",
        "ix_alerts_anomaly_id",
        "ix_alerts_event_id",
        "ix_alerts_severity",
        "ix_alerts_created_at",
        "ix_alerts_status",
        "uq_alerts_transaction_policy",
    }
