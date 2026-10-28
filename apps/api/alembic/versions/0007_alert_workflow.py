"""Add alert investigation state, version checks, and audit history.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alerts", sa.Column("status", sa.String(24), server_default="open", nullable=False)
    )
    op.add_column("alerts", sa.Column("assignee", sa.String(128), nullable=True))
    op.add_column("alerts", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.add_column(
        "alerts",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_check_constraint(
        op.f("ck_alerts_valid_status"),
        "alerts",
        "status IN ('open', 'acknowledged', 'resolved', 'false_positive')",
    )
    op.create_check_constraint(op.f("ck_alerts_positive_version"), "alerts", "version >= 1")
    op.create_table(
        "alert_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_audit")),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            ondelete="CASCADE",
            name=op.f("fk_alert_audit_alert_id_alerts"),
        ),
        sa.UniqueConstraint("alert_id", "version", name="uq_alert_audit_version"),
    )
    op.create_index("ix_alert_audit_alert_id", "alert_audit", ["alert_id"])
    op.execute("""INSERT INTO alert_audit
        (id, alert_id, version, action, actor, reason, "before", "after", created_at)
        SELECT gen_random_uuid(), id, 1, 'import', 'system:migration',
        'Existing alert initialized as open; earlier workflow history is unavailable',
        NULL, json_build_object('status', 'open', 'assignee', NULL, 'version', 1), now()
        FROM alerts""")


def downgrade() -> None:
    op.drop_table("alert_audit")
    op.drop_constraint(op.f("ck_alerts_positive_version"), "alerts", type_="check")
    op.drop_constraint(op.f("ck_alerts_valid_status"), "alerts", type_="check")
    op.drop_index("ix_alerts_status", table_name="alerts")
    for column in ("updated_at", "version", "assignee", "status"):
        op.drop_column("alerts", column)
