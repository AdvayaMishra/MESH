"""Bounded normalized source, pseudonymous IP/device and structured telemetry metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"


def upgrade():
    op.add_column(
        "security_events", sa.Column("context", sa.JSON(), nullable=False, server_default="{}")
    )
    op.create_index(
        "ix_event_org_category_time",
        "security_events",
        ["organization_id", "category", "occurred_at", "id"],
    )


def downgrade():
    raise RuntimeError("Telemetry metadata retirement requires a reviewed recovery migration")
