"""Retain model and operator pricing provenance on each AI usage record."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade():
    op.add_column("ai_usage", sa.Column("model", sa.String(100), nullable=True))
    op.add_column("ai_usage", sa.Column("billing_currency", sa.String(3), nullable=True))
    op.add_column("ai_usage", sa.Column("pricing", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError("Destructive downgrade requires a reviewed recovery migration")
