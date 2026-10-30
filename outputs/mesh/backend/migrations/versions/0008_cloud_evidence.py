"""Retain cloud assessment uncertainty/coverage and prevent snapshot mutation."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade():
    for column in ("errors", "coverage", "limitations"):
        op.add_column("cloud_assessments", sa.Column(column, sa.JSON(), nullable=True))
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON cloud_assessments FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
        )


def downgrade():
    raise RuntimeError("Destructive downgrade requires a reviewed recovery migration")
