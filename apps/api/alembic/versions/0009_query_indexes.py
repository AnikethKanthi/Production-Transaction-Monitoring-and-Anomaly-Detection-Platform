"""Cover stable time ordering for common transaction filters and the alert queue."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_transactions_status_occurred_at", table_name="transactions")
    op.create_index(
        "ix_transactions_status_occurred_at", "transactions", ["status", "occurred_at", "id"]
    )
    op.create_index(
        "ix_transactions_currency_occurred_at_id", "transactions", ["currency", "occurred_at", "id"]
    )
    op.create_index("ix_alerts_status_created_at_id", "alerts", ["status", "created_at", "id"])


def downgrade():
    op.drop_index("ix_alerts_status_created_at_id", table_name="alerts")
    op.drop_index("ix_transactions_currency_occurred_at_id", table_name="transactions")
    op.drop_index("ix_transactions_status_occurred_at", table_name="transactions")
    op.create_index("ix_transactions_status_occurred_at", "transactions", ["status", "occurred_at"])
