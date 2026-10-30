"""Actor/body-bound financial cost receipts; historical receipt provenance stays unknown."""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"


def upgrade():
    with op.batch_alter_table("cost_records") as batch:
        batch.add_column(sa.Column("request_key", sa.String(36), nullable=True))
        batch.add_column(sa.Column("request_digest", sa.String(64), nullable=True))
        batch.add_column(sa.Column("recorded_by", sa.String(36), nullable=True))
        batch.add_column(sa.Column("billing_provider", sa.String(10), nullable=True))
        batch.add_column(sa.Column("usage_quantity", sa.Numeric(20, 6), nullable=True))
        batch.add_column(sa.Column("usage_unit", sa.String(20), nullable=True))
        batch.create_unique_constraint("uq_cost_request_key", ["organization_id", "request_key"])
        batch.create_foreign_key(
            "fk_cost_actor_tenant",
            "memberships",
            ["organization_id", "recorded_by"],
            ["organization_id", "user_id"],
        )
        batch.create_check_constraint(
            "ck_cost_receipt_complete",
            "(request_key IS NULL AND request_digest IS NULL AND recorded_by IS NULL) OR (request_key IS NOT NULL AND request_digest IS NOT NULL AND recorded_by IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_cost_request_key_length", "request_key IS NULL OR length(request_key)=36"
        )
        batch.create_check_constraint(
            "ck_cost_digest_length", "request_digest IS NULL OR length(request_digest)=64"
        )
        batch.create_check_constraint(
            "ck_cost_usage_pair",
            "(usage_quantity IS NULL AND usage_unit IS NULL) OR (usage_quantity IS NOT NULL AND usage_unit IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_cost_usage_nonnegative", "usage_quantity IS NULL OR usage_quantity >= 0"
        )
        batch.create_index(
            "ix_cost_org_currency_period", ["organization_id", "currency", "period", "department"]
        )


def downgrade():
    raise RuntimeError("Financial receipt retirement requires a reviewed recovery migration")
