"""Explicit employee/year holiday exclusions; preserve existing allowance behavior."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade():
    op.add_column(
        "leave_entitlements",
        sa.Column("holidays", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade():
    raise RuntimeError("Destructive downgrade requires a reviewed recovery migration")
