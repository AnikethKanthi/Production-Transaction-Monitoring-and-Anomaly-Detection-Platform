"""Create transactions and processed events.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", sa.String(128), nullable=False),
        sa.Column("merchant_id", sa.String(128), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_transactions_positive_amount")),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_transactions_currency_code"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name=op.f("ck_transactions_valid_status"),
        ),
    )
    op.create_index("ix_transactions_occurred_at_id", "transactions", ["occurred_at", "id"])
    op.create_index(
        "ix_transactions_account_id_occurred_at", "transactions", ["account_id", "occurred_at"]
    )
    op.create_index("ix_transactions_status_occurred_at", "transactions", ["status", "occurred_at"])
    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_processed_events")),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_processed_events_transaction_id_transactions"),
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_processed_events_transaction_id", "processed_events", ["transaction_id"])
    op.create_index("ix_processed_events_processed_at", "processed_events", ["processed_at"])


def downgrade() -> None:
    op.drop_table("processed_events")
    op.drop_table("transactions")
