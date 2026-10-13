"""Add transaction country.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("country", sa.String(2), nullable=True))
    # Revision 0001 may already contain data. Backfill before making the field required.
    op.execute("UPDATE transactions SET country = 'US' WHERE country IS NULL")
    op.alter_column("transactions", "country", nullable=False)
    op.create_check_constraint(
        op.f("ck_transactions_country_code"), "transactions", "country ~ '^[A-Z]{2}$'"
    )
    op.create_index(
        "ix_transactions_country_occurred_at", "transactions", ["country", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_country_occurred_at", table_name="transactions")
    op.drop_constraint(op.f("ck_transactions_country_code"), "transactions", type_="check")
    op.drop_column("transactions", "country")
