"""Create deduplicated alerts with policy evidence.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("anomaly_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            ondelete="CASCADE",
            name=op.f("fk_alerts_transaction_id_transactions"),
        ),
        sa.ForeignKeyConstraint(
            ["anomaly_id"],
            ["anomalies.id"],
            ondelete="CASCADE",
            name=op.f("fk_alerts_anomaly_id_anomalies"),
        ),
        sa.UniqueConstraint(
            "transaction_id", "policy_version", name="uq_alerts_transaction_policy"
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name=op.f("ck_alerts_valid_severity"),
        ),
    )
    for column in ("transaction_id", "anomaly_id", "event_id", "severity", "created_at"):
        op.create_index(f"ix_alerts_{column}", "alerts", [column])


def downgrade() -> None:
    op.drop_table("alerts")
