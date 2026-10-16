"""Add transaction context and stored inference features.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("device_id", sa.String(128), nullable=True))
    op.add_column("transactions", sa.Column("ip_address", sa.String(128), nullable=True))
    op.add_column("transactions", sa.Column("payment_method", sa.String(128), nullable=True))
    op.add_column("transactions", sa.Column("order_amount", sa.Numeric(18, 2), nullable=True))
    op.create_table(
        "inference_features",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("feature_definition_version", sa.String(64), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inference_features")),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_inference_features_transaction_id_transactions"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "transaction_id",
            "feature_definition_version",
            name=op.f("uq_inference_features_version"),
        ),
    )
    op.create_index(
        "ix_inference_features_transaction_id", "inference_features", ["transaction_id"]
    )
    op.create_index("ix_inference_features_event_id", "inference_features", ["event_id"])


def downgrade() -> None:
    op.drop_table("inference_features")
    op.drop_column("transactions", "order_amount")
    op.drop_column("transactions", "payment_method")
    op.drop_column("transactions", "ip_address")
    op.drop_column("transactions", "device_id")
