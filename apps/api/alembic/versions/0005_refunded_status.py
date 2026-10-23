"""Allow refunded transactions.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_transactions_valid_status"), "transactions", type_="check")
    op.create_check_constraint(
        op.f("ck_transactions_valid_status"),
        "transactions",
        "status IN ('pending', 'completed', 'failed', 'refunded')",
    )


def downgrade() -> None:
    op.execute("UPDATE transactions SET status = 'failed' WHERE status = 'refunded'")
    op.drop_constraint(op.f("ck_transactions_valid_status"), "transactions", type_="check")
    op.create_check_constraint(
        op.f("ck_transactions_valid_status"),
        "transactions",
        "status IN ('pending', 'completed', 'failed')",
    )
