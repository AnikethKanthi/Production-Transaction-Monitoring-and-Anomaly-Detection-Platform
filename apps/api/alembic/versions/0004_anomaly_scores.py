"""Store transaction anomaly scores.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "anomalies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("scoring_status", sa.String(16), nullable=False),
        sa.Column("failure_reason", sa.String(512), nullable=True),
        sa.Column("inference_latency_seconds", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_anomalies")),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_anomalies_transaction_id_transactions"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("transaction_id", name=op.f("uq_anomalies_transaction_id")),
        sa.CheckConstraint(
            "scoring_status IN ('scored', 'fallback')",
            name=op.f("ck_anomalies_scoring_status"),
        ),
        sa.CheckConstraint(
            "inference_latency_seconds >= 0",
            name=op.f("ck_anomalies_nonnegative_latency"),
        ),
    )
    op.create_index("ix_anomalies_model_version", "anomalies", ["model_version"])
    op.create_index("ix_anomalies_created_at", "anomalies", ["created_at"])


def downgrade() -> None:
    op.drop_table("anomalies")
