"""Index ingestion timestamps for rolling operational metrics."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_transactions_created_at", "transactions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_transactions_created_at", table_name="transactions")
