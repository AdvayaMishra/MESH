"""Retain reasons for withdrawing unapplied salary changes."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade():
    op.add_column(
        "employment_changes", sa.Column("resolution_reason", sa.String(1000), nullable=True)
    )
    op.add_column(
        "employment_changes", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    raise RuntimeError("Destructive downgrade requires a reviewed recovery migration")
