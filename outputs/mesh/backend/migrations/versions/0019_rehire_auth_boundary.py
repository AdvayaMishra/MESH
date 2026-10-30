"""Fresh JWT boundary for reviewed employee rehire; existing memberships stay unchanged."""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"


def upgrade():
    op.add_column(
        "memberships", sa.Column("access_not_before", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    raise RuntimeError(
        "Removing rehire authentication boundaries requires a reviewed recovery migration"
    )
